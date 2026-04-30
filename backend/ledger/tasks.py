import random, logging
from datetime import timedelta
from celery import shared_task
from django.utils import timezone
from django.db import transaction
from .models import Payout
from .state_machine import PayoutStateMachine, InvalidTransitionError

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3
PROCESSING_TIMEOUT_SECONDS = 30


@shared_task(bind=True, max_retries=MAX_ATTEMPTS)
def process_payout(self, payout_id: str):
    try:
        payout = Payout.objects.get(pk=payout_id)
    except Payout.DoesNotExist:
        logger.error(f"Payout {payout_id} does not exist")
        return

    if payout.status != Payout.PENDING:
        logger.warning(f"Payout {payout_id} is not pending; current status is {payout.status}")
        return

    try:
        PayoutStateMachine.transition(payout_id, Payout.PROCESSING)
    except InvalidTransitionError as e:
        logger.error(f"Invalid transition for payout {payout_id}: {e}")
        return

    outcome = random.random()

    if outcome < 0.70:
        try:
            PayoutStateMachine.transition(payout_id, Payout.COMPLETED)
        except InvalidTransitionError as e:
            logger.error(f"Invalid transition for payout {payout_id}: {e}")
            return
    elif outcome < 0.90:
        reason = "Bank rejected: insufficient beneficiary details"
        try:
            PayoutStateMachine.transition(payout_id, Payout.FAILED, failure_reason=reason)
        except InvalidTransitionError as e:
            logger.error(f"Invalid transition for payout {payout_id}: {e}")
            return
    else:
        logger.warning(f"Payout {payout_id} simulated hang; left in PROCESSING")


@shared_task
def process_pending_payouts(limit: int = 50):
    pending_ids = list(
        Payout.objects.filter(status=Payout.PENDING)
        .order_by('created_at')
        .values_list('id', flat=True)[:limit]
    )
    for payout_id in pending_ids:
        process_payout.apply_async(args=[str(payout_id)])


@shared_task
def retry_stuck_payouts():
    timeout_threshold = timezone.now() - timedelta(seconds=PROCESSING_TIMEOUT_SECONDS)

    stuck_payouts = Payout.objects.filter(
        status=Payout.PROCESSING,
        processing_started_at__lt=timeout_threshold,
    ).select_for_update(skip_locked=True)
    # skip_locked=True skips rows already locked by another worker and prevents double-retry.

    with transaction.atomic():
        for payout in stuck_payouts:
            if payout.attempt_count >= MAX_ATTEMPTS:
                PayoutStateMachine.transition(
                    str(payout.id), Payout.FAILED,
                    failure_reason=f"Max retries ({MAX_ATTEMPTS}) exceeded"
                )
                logger.error(f"Payout {payout.id} permanently failed after {MAX_ATTEMPTS} attempts")
            else:
                # Exponential backoff: 2^attempt_count seconds (4s, 8s, 16s)
                backoff = 2 ** payout.attempt_count
                # Direct update bypasses the state machine guard. This is the only legitimate exception,
                # used by the recovery task to reset a stuck PROCESSING payout back to PENDING for retry.
                Payout.objects.filter(pk=payout.id).update(status=Payout.PENDING)
                process_payout.apply_async(args=[str(payout.id)], countdown=backoff)
                logger.info(f"Retrying payout {payout.id} in {backoff}s (attempt {payout.attempt_count + 1})")
