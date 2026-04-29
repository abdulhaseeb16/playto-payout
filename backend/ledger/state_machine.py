from django.db import transaction
from django.utils import timezone
from .models import Payout, LedgerEntry


class InvalidTransitionError(Exception):
    pass


LEGAL_TRANSITIONS = {
    Payout.PENDING: [Payout.PROCESSING],
    Payout.PROCESSING: [Payout.COMPLETED, Payout.FAILED],
    Payout.COMPLETED: [],    # terminal; empty list blocks all exits
    Payout.FAILED: [],       # terminal; empty list blocks failed -> completed
}


class PayoutStateMachine:

    @staticmethod
    def validate_transition(current_status: str, new_status: str):
        """
        Raises InvalidTransitionError if the transition is illegal.
        FAILED maps to [] so failed -> completed raises here.
        COMPLETED maps to [] so completed -> anything raises here.
        """
        allowed = LEGAL_TRANSITIONS.get(current_status, [])
        if new_status not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition payout from '{current_status}' to '{new_status}'. "
                f"Allowed from '{current_status}': {allowed or ['none (terminal state)']}"
            )

    @staticmethod
    def transition(payout_id: str, new_status: str, failure_reason: str = ''):
        """
        Atomically transitions a payout status.

        On FAILED: creates a credit LedgerEntry to release the hold in the SAME
        transaction. If anything fails mid-way, both the status change and
        the credit are rolled back together; merchant never gets a partial state.

        On COMPLETED: only records the terminal status. The debit was already
        written when the payout was created and the funds were reserved.

        Uses select_for_update() to lock the payout row and prevent
        concurrent transitions on the same payout.
        """
        with transaction.atomic():
            payout = Payout.objects.select_for_update().get(pk=payout_id)

            PayoutStateMachine.validate_transition(payout.status, new_status)

            payout.status = new_status

            if new_status == Payout.PROCESSING:
                payout.processing_started_at = timezone.now()
                payout.attempt_count += 1

            if new_status == Payout.FAILED:
                payout.failure_reason = failure_reason
                LedgerEntry.objects.create(
                    merchant=payout.merchant,
                    entry_type=LedgerEntry.CREDIT,
                    amount_paise=payout.amount_paise,
                    description=f"Refund for failed payout {payout.id}: {failure_reason}",
                    reference_id=payout.id,
                )

            payout.save()
            return payout
