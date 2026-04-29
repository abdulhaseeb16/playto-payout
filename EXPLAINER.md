# EXPLAINER.md

## 1. The Ledger

Balance is derived from ledger rows, never from a stored balance column:

```python
result = self.ledger_entries.aggregate(
    total_credits=Sum('amount_paise', filter=Q(entry_type=LedgerEntry.CREDIT)),
    total_debits=Sum('amount_paise', filter=Q(entry_type=LedgerEntry.DEBIT)),
)
balance = (result['total_credits'] or 0) - (result['total_debits'] or 0)
```

That compiles to one database aggregation over `ledger_ledgerentry`. Credits and debits live in one append-only table so the audit trail is complete and the invariant is simple:

```text
balance = SUM(credits) - SUM(debits)
```

Amounts are stored as integer paise in `BigIntegerField`, avoiding float rounding and avoiding a mutable balance that can drift.

## 2. The Lock

Payout creation locks the merchant row while computing availability and creating the payout:

```python
with transaction.atomic():
    merchant_locked = Merchant.objects.select_for_update().get(pk=merchant_id)
    result = LedgerEntry.objects.filter(merchant=merchant_locked).aggregate(...)
    available = (result['credits'] or 0) - (result['debits'] or 0)
    if available < amount_paise:
        raise InsufficientFundsError(...)
    payout = Payout.objects.create(...)
    LedgerEntry.objects.create(..., entry_type=LedgerEntry.DEBIT, reference_id=payout.id)
```

`select_for_update()` maps to PostgreSQL `SELECT ... FOR UPDATE`. A second payout request for the same merchant blocks until the first transaction commits or rolls back, so two concurrent requests cannot both read the same available balance and overdraw the merchant.

Pending and processing payouts are still reported as `held_paise`, but the hold is now also reflected in the append-only ledger as a debit at payout creation. Because the ledger already includes reserved funds, `available_paise` is the current ledger balance rather than `ledger balance - held`.

## 3. The Idempotency

The system stores an `IdempotencyKey` row scoped by `(merchant, key)`. The row contains:

- `request_hash`: SHA-256 of the canonical request body
- `response_body`: exact JSON response to replay
- `response_status`: exact HTTP status to replay
- `expires_at`: 24-hour TTL

Flow:

1. Missing or invalid `Idempotency-Key` is rejected.
2. Existing unexpired key with the same request hash and stored response is replayed.
3. Existing key with a different request hash returns `409`.
4. Existing key with `response_status=0` returns `409` because the first request is still in flight.
5. A new key creates a placeholder row. The database unique constraint handles simultaneous first requests.

The relevant implementation is in `ledger/idempotency.py` and is called from `PayoutCreateView`.

## 4. The State Machine

Legal transitions are centralized:

```python
LEGAL_TRANSITIONS = {
    Payout.PENDING: [Payout.PROCESSING],
    Payout.PROCESSING: [Payout.COMPLETED, Payout.FAILED],
    Payout.COMPLETED: [],
    Payout.FAILED: [],
}
```

`FAILED` and `COMPLETED` are terminal. `failed -> completed` is blocked because `FAILED` maps to an empty list, so `validate_transition()` raises `InvalidTransitionError`.

All normal status changes go through `PayoutStateMachine.transition()`, which locks the payout row using `select_for_update()`. Payout creation writes the debit ledger entry that reserves funds. A completed payout only moves to the terminal status because the debit already exists. A failed payout atomically writes a refund credit for the same payout reference, releasing the reserved funds in the ledger.

The recovery task has one documented exception: it may reset a stuck `PROCESSING` payout to `PENDING` for retry before the payout has reached a terminal state.

## 5. The AI Audit

Wrong code pattern caught:

```python
merchant = Merchant.objects.get(pk=merchant_id)
available = merchant.get_available_balance()
if available >= amount_paise:
    Payout.objects.create(...)
```

That is a time-of-check/time-of-use race. Two concurrent requests can both read the same balance before either creates a payout.

Replacement:

```python
with transaction.atomic():
    merchant_locked = Merchant.objects.select_for_update().get(pk=merchant_id)
    available = compute_ledger_balance_inside_transaction(merchant_locked)
    if available < amount_paise:
        raise InsufficientFundsError(...)
    payout = Payout.objects.create(...)
    LedgerEntry.objects.create(..., entry_type=LedgerEntry.DEBIT, reference_id=payout.id)
```

The database lock serializes payout creation per merchant, which is the critical correctness property for money movement.
