import uuid

from django.db import models
from django.db.models import Sum, Q
from django.utils import timezone


class Merchant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def get_balance(self):
        """
        Derives balance entirely at database level using a single aggregation.
        NEVER fetches rows and sums in Python.
        """
        result = self.ledger_entries.aggregate(
            total_credits=Sum('amount_paise', filter=Q(entry_type=LedgerEntry.CREDIT)),
            total_debits=Sum('amount_paise', filter=Q(entry_type=LedgerEntry.DEBIT)),
        )
        return (result['total_credits'] or 0) - (result['total_debits'] or 0)

    def get_held_balance(self):
        """Funds locked by pending/processing payouts."""
        result = self.payouts.filter(
            status__in=[Payout.PENDING, Payout.PROCESSING]
        ).aggregate(total=Sum('amount_paise'))
        return result['total'] or 0

    def get_available_balance(self):
        return self.get_balance()

    def __str__(self):
        return self.name


class BankAccount(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, related_name='bank_accounts')
    account_number = models.CharField(max_length=20)
    ifsc_code = models.CharField(max_length=11)
    account_holder_name = models.CharField(max_length=255)
    is_primary = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.account_holder_name} - {self.account_number[-4:]}"


class LedgerEntry(models.Model):
    CREDIT = 'credit'
    DEBIT = 'debit'
    ENTRY_TYPE_CHOICES = [(CREDIT, 'Credit'), (DEBIT, 'Debit')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, on_delete=models.PROTECT, related_name='ledger_entries')
    entry_type = models.CharField(max_length=6, choices=ENTRY_TYPE_CHOICES)
    amount_paise = models.BigIntegerField()   # NEVER FloatField. NEVER DecimalField.
    description = models.CharField(max_length=500)
    reference_id = models.UUIDField(null=True, blank=True)   # links to Payout.id
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['merchant', '-created_at']),
            models.Index(fields=['merchant', 'entry_type']),
        ]


class Payout(models.Model):
    PENDING = 'pending'
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    FAILED = 'failed'

    STATUS_CHOICES = [
        (PENDING, 'Pending'), (PROCESSING, 'Processing'),
        (COMPLETED, 'Completed'), (FAILED, 'Failed'),
    ]

    LEGAL_TRANSITIONS = {
        PENDING: [PROCESSING],
        PROCESSING: [COMPLETED, FAILED],
        COMPLETED: [],     # terminal
        FAILED: [],        # terminal
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, on_delete=models.PROTECT, related_name='payouts')
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT)
    amount_paise = models.BigIntegerField()   # NEVER FloatField. NEVER DecimalField.
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    attempt_count = models.IntegerField(default=0)
    idempotency_key = models.CharField(max_length=36, db_index=True)
    failure_reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = [('merchant', 'idempotency_key')]   # idempotency scoped per merchant
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['merchant', 'status']),
        ]

    def __str__(self):
        return f"Payout {self.id} - {self.status} - {self.amount_paise}p"


class IdempotencyKey(models.Model):
    """
    Stores exact response for replay. Scoped per merchant. Expires after 24 hours.
    response_status=0 means the first request is still in-flight.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE)
    key = models.CharField(max_length=36)
    request_hash = models.CharField(max_length=64)   # SHA-256 of request body
    response_body = models.JSONField()               # exact response to replay
    response_status = models.IntegerField()          # 0 means in-flight
    payout = models.OneToOneField(Payout, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        unique_together = [('merchant', 'key')]
        indexes = [models.Index(fields=['expires_at'])]

    @classmethod
    def is_expired(cls, instance):
        return timezone.now() > instance.expires_at

    def __str__(self):
        return f"IdempotencyKey {self.key} for {self.merchant}"
