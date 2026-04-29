import json
import logging
import uuid

from django.db import transaction
from django.db.models import Q, Sum
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .idempotency import prepare_idempotency_record, store_idempotency_response
from .models import BankAccount, LedgerEntry, Merchant, Payout
from .serializers import MerchantDashboardSerializer, PayoutSerializer
from .tasks import process_payout

logger = logging.getLogger(__name__)


class InsufficientFundsError(Exception):
    pass


def make_json_safe(data):
    return json.loads(json.dumps(data, default=str))


class APIIndexView(APIView):
    def get(self, request):
        merchants = Merchant.objects.order_by('name')
        return Response({
            'name': 'Playto Payout API',
            'version': 'v1',
            'endpoints': {
                'merchant_dashboard': '/api/v1/merchants/<merchant_id>/dashboard/',
                'create_payout_flat': '/api/v1/payouts/',
                'create_payout': '/api/v1/merchants/<merchant_id>/payouts/',
                'payout_detail': '/api/v1/merchants/<merchant_id>/payouts/<payout_id>/',
            },
            'seeded_merchants': [
                {
                    'id': str(merchant.id),
                    'name': merchant.name,
                    'dashboard': f'/api/v1/merchants/{merchant.id}/dashboard/',
                }
                for merchant in merchants
            ],
        })


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
    def post(self, request, merchant_id=None):
        idempotency_key_header = request.headers.get('Idempotency-Key')
        if not idempotency_key_header:
            return Response({'error': 'Idempotency-Key header is required'}, status=400)

        try:
            uuid.UUID(idempotency_key_header)
        except ValueError:
            return Response({'error': 'Idempotency-Key must be a valid UUID'}, status=400)

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

        if merchant_id is None:
            try:
                bank_account = BankAccount.objects.select_related('merchant').get(id=bank_account_id)
            except (BankAccount.DoesNotExist, ValueError):
                return Response({'error': 'Invalid bank_account_id'}, status=400)
            merchant = bank_account.merchant
            merchant_id = merchant.id
        else:
            try:
                merchant = Merchant.objects.get(pk=merchant_id)
            except Merchant.DoesNotExist:
                return Response({'error': 'Merchant not found'}, status=404)

        idem_record, replay_response = prepare_idempotency_record(
            merchant,
            idempotency_key_header,
            {'amount_paise': amount_paise, 'bank_account_id': str(bank_account_id)},
        )
        if replay_response is not None:
            return replay_response

        try:
            with transaction.atomic():
                merchant_locked = Merchant.objects.select_for_update().get(pk=merchant_id)

                result = LedgerEntry.objects.filter(merchant=merchant_locked).aggregate(
                    credits=Sum('amount_paise', filter=Q(entry_type=LedgerEntry.CREDIT)),
                    debits=Sum('amount_paise', filter=Q(entry_type=LedgerEntry.DEBIT)),
                )
                ledger_balance = (result['credits'] or 0) - (result['debits'] or 0)

                available = ledger_balance
                if available < amount_paise:
                    raise InsufficientFundsError(
                        f'Insufficient funds: {available}p available, {amount_paise}p requested'
                    )

                try:
                    bank_account = BankAccount.objects.get(
                        id=bank_account_id,
                        merchant=merchant_locked,
                    )
                except BankAccount.DoesNotExist:
                    raise ValueError('Invalid bank_account_id')

                payout = Payout.objects.create(
                    merchant=merchant_locked,
                    bank_account=bank_account,
                    amount_paise=amount_paise,
                    idempotency_key=idempotency_key_header,
                    status=Payout.PENDING,
                )
                LedgerEntry.objects.create(
                    merchant=merchant_locked,
                    entry_type=LedgerEntry.DEBIT,
                    amount_paise=amount_paise,
                    description=f"Payout hold: {payout.id}",
                    reference_id=payout.id,
                )

        except InsufficientFundsError as e:
            response_body = {'error': str(e)}
            store_idempotency_response(idem_record, response_body, 422)
            return Response(response_body, status=422)

        except ValueError as e:
            response_body = {'error': str(e)}
            store_idempotency_response(idem_record, response_body, 400)
            return Response(response_body, status=400)

        try:
            process_payout.apply_async(args=[str(payout.id)], countdown=1)
        except Exception as exc:
            logger.exception('Failed to enqueue payout processing for payout %s: %s', payout.id, exc)

        response_data = make_json_safe(PayoutSerializer(payout).data)
        store_idempotency_response(idem_record, response_data, 201, payout=payout)

        return Response(response_data, status=201)


class PayoutDetailView(APIView):
    def get(self, request, merchant_id, payout_id):
        try:
            payout = Payout.objects.get(pk=payout_id, merchant_id=merchant_id)
        except Payout.DoesNotExist:
            return Response({'error': 'Payout not found'}, status=404)

        return Response(PayoutSerializer(payout).data)
