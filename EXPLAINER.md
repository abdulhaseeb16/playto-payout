# EXPLAINER.md

## 1. The Ledger

Balance calculation query:

```python
result = self.ledger_entries.aggregate(
    total_credits=Sum('amount_paise', filter=Q(entry_type=LedgerEntry.CREDIT)),
    total_debits=Sum('amount_paise', filter=Q(entry_type=LedgerEntry.DEBIT)),
)
balance = (result['total_credits'] or 0) - (result['total_debits'] or 0)
```

This produces the SQL:
SELECT
  SUM(amount_paise) FILTER (WHERE entry_type = 'credit') AS total_credits,
  SUM(amount_paise) FILTER (WHERE entry_type = 'debit')  AS total_debits
FROM ledger_ledgerentry
WHERE merchant_id = %s;

I modelled it this way because a stored balance column can drift silently
if any code path writes a ledger entry but forgets to update it.
With a derived balance, the invariant SUM(credits) - SUM(debits) = balance
holds by construction and can be verified at any time by re-running the query.

## 2. The Lock

```python
with transaction.atomic():
    merchant_locked = Merchant.objects.select_for_update().get(pk=merchant_id)
    # All balance checks and payout creation happen inside this block
```

select_for_update() translates to SELECT ... FOR UPDATE in PostgreSQL.
This acquires a row-level exclusive lock on the merchant row.
Any other transaction attempting select_for_update on the same merchant
will BLOCK until this transaction commits or rolls back.
This serialises concurrent payout requests for the same merchant into a queue:
one check-then-deduct completes fully before the next one can even read the balance.
Without this, two threads can both read 100 rupees, both pass the >= 60 check,
and both create payouts — the classic TOCTOU race condition.

## 3. The Idempotency

The system uses a two-layer guard:
Layer 1: A database lookup for an existing IdempotencyKey row for (merchant, key)
         that is not expired (expires_at > now()) and has a stored response
         (response_status != 0). If found, replay the stored response immediately.
Layer 2: The unique_together = [('merchant', 'key')] constraint on IdempotencyKey.
         If the first request is still in-flight (response_status = 0 placeholder exists),
         a second concurrent request attempts to INSERT and hits IntegrityError.
         It catches this and returns 409.

This handles all three cases:
  - Clean replay: key exists, response stored → replay
  - In-flight race: key exists, response_status=0 → 409 retry-later
  - Simultaneous new: both try INSERT → one wins, one catches IntegrityError → 409

Keys expire after 24 hours via expires_at field filtered on every lookup.

## 4. The State Machine

```python
LEGAL_TRANSITIONS = {
    Payout.PENDING: [Payout.PROCESSING],
    Payout.PROCESSING: [Payout.COMPLETED, Payout.FAILED],
    Payout.COMPLETED: [],    # terminal — empty list blocks ALL exits
    Payout.FAILED: [],       # terminal — empty list blocks failed→completed
}

def validate_transition(current_status: str, new_status: str):
    allowed = LEGAL_TRANSITIONS.get(current_status, [])
    if new_status not in allowed:
        raise InvalidTransitionError(...)
```

failed→completed is blocked because FAILED maps to an empty list [].
Any transition attempt out of FAILED (including to COMPLETED) hits
`if new_status not in []` which is always True → InvalidTransitionError raised.
All status changes in the codebase — views and tasks — call
PayoutStateMachine.transition() which calls validate_transition() first.
There is no direct payout.status = 'x' assignment anywhere outside this class,
except the documented internal recovery reset in retry_stuck_payouts().

On FAILED, the state machine only writes a refund credit if a debit ledger entry
already exists for that payout reference. This preserves the guide's atomic
refund pattern without minting balance when a payout failed before settlement.

## 5. The AI Audit

What AI generated:
```python
# AI suggested this for the concurrency check
merchant = Merchant.objects.get(pk=merchant_id)
available = merchant.get_available_balance()  # Python call, outside any lock
if available >= amount_paise:
    payout = Payout.objects.create(...)
```

What I caught: TOCTOU race condition. Two requests can both call
get_available_balance() concurrently, both see 100 rupees, both pass the check,
both create payouts. The merchant is overdrafted. The AI optimised for the
single-request happy path, not concurrent production traffic.

What I replaced it with:
```python
with transaction.atomic():
    merchant_locked = Merchant.objects.select_for_update().get(pk=merchant_id)
    # compute balance at DB level, inside the lock
    result = LedgerEntry.objects.filter(merchant=merchant_locked).aggregate(
        credits=Sum('amount_paise', filter=Q(entry_type=LedgerEntry.CREDIT)),
        debits=Sum('amount_paise', filter=Q(entry_type=LedgerEntry.DEBIT)),
    )
    ledger_balance = (result['credits'] or 0) - (result['debits'] or 0)
    held = Payout.objects.filter(
        merchant=merchant_locked,
        status__in=[Payout.PENDING, Payout.PROCESSING]
    ).aggregate(total=Sum('amount_paise'))['total'] or 0
    available = ledger_balance - held
    if available < amount_paise:
        raise InsufficientFundsError(...)
    payout = Payout.objects.create(...)
```

The select_for_update() + transaction.atomic() means only one thread executes
the check-and-create sequence at a time per merchant.
