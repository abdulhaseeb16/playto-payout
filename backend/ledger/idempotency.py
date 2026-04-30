import hashlib
import json
from datetime import timedelta

from django.db import transaction, IntegrityError
from django.utils import timezone
from rest_framework.response import Response

from .models import IdempotencyKey

IDEMPOTENCY_TTL_HOURS = 24


def get_request_hash(body: dict) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()


def get_or_create_idempotency_key(merchant, key: str, request_hash: str):
    """
    Returns (idem_key_instance, is_new: bool).

    Uses get_or_create inside a transaction. If two concurrent NEW requests
    arrive for the same key simultaneously, only one INSERT will win.
    The loser catches IntegrityError and fetches the winner's row.
    This is the database-level guard against duplicate processing.
    """
    expires_at = timezone.now() + timedelta(hours=IDEMPOTENCY_TTL_HOURS)
    try:
        with transaction.atomic():
            obj, created = IdempotencyKey.objects.get_or_create(
                merchant=merchant,
                key=key,
                defaults={
                    'request_hash': request_hash,
                    'response_body': {},
                    'response_status': 0,   # 0 = placeholder, request in-flight
                    'expires_at': expires_at,
                }
            )
            return obj, created
    except IntegrityError:
        # Race: two threads both tried to INSERT the same new key simultaneously.
        # The loser fetches the winner's row instead.
        obj = IdempotencyKey.objects.get(merchant=merchant, key=key)
        return obj, False


def prepare_idempotency_record(merchant, key: str, request_body: dict):
    """
    Returns (record, replay_response).
    replay_response is a DRF Response when business logic should not run.
    """
    request_hash = get_request_hash(request_body)

    existing = IdempotencyKey.objects.filter(merchant=merchant, key=key).first()
    if existing:
        if IdempotencyKey.is_expired(existing):
            existing.delete()
        elif existing.request_hash != request_hash:
            return None, Response(
                {'error': 'Idempotency-Key was already used with a different request body.'},
                status=409,
            )
        elif existing.response_status != 0:
            return existing, Response(existing.response_body, status=existing.response_status)
        else:
            return existing, Response(
                {'error': 'A request with this idempotency key is already being processed.'},
                status=409,
            )

    record, created = get_or_create_idempotency_key(merchant, key, request_hash)
    if not created:
        if record.request_hash != request_hash:
            return None, Response(
                {'error': 'Idempotency-Key was already used with a different request body.'},
                status=409,
            )
        if record.response_status != 0:
            return record, Response(record.response_body, status=record.response_status)
        return record, Response(
            {'error': 'A request with this idempotency key is already being processed.'},
            status=409,
        )

    return record, None


def store_idempotency_response(record, response_body, response_status, payout=None):
    record.response_body = response_body
    record.response_status = response_status
    if payout is not None:
        record.payout = payout
        record.save(update_fields=['response_body', 'response_status', 'payout'])
    else:
        record.save(update_fields=['response_body', 'response_status'])
