import uuid
import json
from datetime import timedelta
from django.db import transaction, IntegrityError
from django.db.models import Sum, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Merchant, Payout, LedgerEntry, BankAccount, IdempotencyKey
from .serializers import MerchantDashboardSerializer, PayoutSerializer
from .state_machine import PayoutStateMachine, InvalidTransitionError
from .tasks import process_payout


class InsufficientFundsError(Exception):
    pass


def make_json_safe(data):
    return json.loads(json.dumps(data, default=str))


class MerchantDashboardView(APIView):
    def get(self, request, merchant_id):
        try:
            merchant = Merchant.objects.get(pk=merchant_id)
        except Merchant.DoesNotExist:
            return Response({'error': 'Merchant not found'}, status=status.HTTP_404_NOT_FOUND)

        payouts = Payout.objects.filter(merchant=merchant)[:20]
        ledger_entries = LedgerEntry.objects.filter(merchant=merchant)[:30]

        return Response({
            'merchant': MerchantDashboardSerializer(merchant).data,
            'balance': {
                'total_paise': merchant.get_balance(),
                'held_paise': merchant.get_held_balance(),
                'available_paise': merchant.get_available_balance(),
            },
            'payouts': PayoutSerializer(payouts, many=True).data,
            'ledger_entries': [
                {
                    'id': str(entry.id),
                    'type': entry.entry_type,
                    'amount_paise': entry.amount_paise,
                    'description': entry.description,
                    'created_at': entry.created_at.isoformat(),
                }
                for entry in ledger_entries
            ],
        })


class PayoutCreateView(APIView):
    def post(self, request, merchant_id):
        idempotency_key_header = request.headers.get('Idempotency-Key')
        if not idempotency_key_header:
            return Response({'error': 'Idempotency-Key header is required'}, status=400)

        try:
            uuid.UUID(idempotency_key_header)
        except ValueError:
            return Response({'error': 'Idempotency-Key must be a valid UUID'}, status=400)

        try:
            merchant = Merchant.objects.get(pk=merchant_id)
        except Merchant.DoesNotExist:
            return Response({'error': 'Merchant not found'}, status=404)

        amount_paise = request.data.get('amount_paise')
        bank_account_id = request.data.get('bank_account_id')

        if amount_paise is None:
            return Response({'error': 'amount_paise is required'}, status=400)

        try:
            amount_paise = int(amount_paise)
        except (TypeError, ValueError):
            return Response({'error': 'amount_paise must be a positive integer'}, status=400)

        if amount_paise <= 0:
            return Response({'error': 'amount_paise must be a positive integer'}, status=400)

        if not bank_account_id:
            return Response({'error': 'bank_account_id is required'}, status=400)

        # Check for an existing non-expired key
        existing_key = IdempotencyKey.objects.filter(
            merchant=merchant,
            key=idempotency_key_header,
            expires_at__gt=timezone.now()
        ).first()

        if existing_key:
            if existing_key.response_status and existing_key.response_status != 0:
                # We have a stored response — replay it exactly
                return Response(existing_key.response_body, status=existing_key.response_status)
            else:
                # First request is still in-flight — tell caller to retry
                return Response(
                    {'error': 'A request with this idempotency key is already being processed.'},
                    status=409
                )

        # Create placeholder row — unique_together (merchant, key) is the final guard
        # If two concurrent NEW requests arrive, only one INSERT wins; loser gets IntegrityError
        expires_at = timezone.now() + timedelta(hours=24)
        try:
            idem_record = IdempotencyKey.objects.create(
                merchant=merchant,
                key=idempotency_key_header,
                request_hash='',
                response_body={},
                response_status=0,   # 0 = in-flight placeholder
                expires_at=expires_at,
            )
        except IntegrityError:
            return Response(
                {'error': 'A request with this idempotency key is already being processed.'},
                status=409
            )

        try:
            with transaction.atomic():
                # SELECT FOR UPDATE acquires a row-level exclusive lock on this merchant.
                # Any other transaction attempting select_for_update on the same merchant
                # will BLOCK here until this transaction commits or rolls back.
                # This serialises concurrent payout requests and prevents overdraw.
                merchant_locked = Merchant.objects.select_for_update().get(pk=merchant_id)

                # Compute balance INSIDE the lock at database level — never in Python
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
                    raise InsufficientFundsError(
                        f"Insufficient funds: {available}p available, {amount_paise}p requested"
                    )

                try:
                    bank_account = BankAccount.objects.get(
                        id=bank_account_id, merchant=merchant_locked
                    )
                except BankAccount.DoesNotExist:
                    raise ValueError("Invalid bank_account_id")

                payout = Payout.objects.create(
                    merchant=merchant_locked,
                    bank_account=bank_account,
                    amount_paise=amount_paise,
                    idempotency_key=idempotency_key_header,
                    status=Payout.PENDING,
                )

                idem_record.payout = payout
                idem_record.save(update_fields=['payout'])

        except InsufficientFundsError as e:
            response_body = {'error': str(e)}
            idem_record.response_body = response_body
            idem_record.response_status = 422
            idem_record.save(update_fields=['response_body', 'response_status'])
            return Response(response_body, status=422)

        except ValueError as e:
            response_body = {'error': str(e)}
            idem_record.response_body = response_body
            idem_record.response_status = 400
            idem_record.save(update_fields=['response_body', 'response_status'])
            return Response(response_body, status=400)

        try:
            process_payout.apply_async(args=[str(payout.id)], countdown=1)
        except Exception:
            pass

        response_data = make_json_safe(PayoutSerializer(payout).data)
        idem_record.response_body = response_data
        idem_record.response_status = 201
        idem_record.save(update_fields=['response_body', 'response_status'])

        return Response(response_data, status=201)


class PayoutDetailView(APIView):
    def get(self, request, merchant_id, payout_id):
        try:
            payout = Payout.objects.get(pk=payout_id, merchant_id=merchant_id)
        except Payout.DoesNotExist:
            return Response({'error': 'Payout not found'}, status=404)

        return Response(PayoutSerializer(payout).data)
