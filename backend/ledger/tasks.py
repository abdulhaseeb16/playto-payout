from celery import shared_task


@shared_task
def retry_stuck_payouts():
    return {'retried': 0}
