exec(r'''
import uuid
from datetime import timedelta

from django.utils import timezone

from ledger.models import BankAccount, IdempotencyKey, LedgerEntry, Merchant, Payout


MERCHANTS = [
    {'id': '11111111-1111-4111-8111-111111111111', 'name': 'Velocity Creative Agency', 'email': 'ops@velocityagency.in', 'account_number': '001234567890', 'ifsc_code': 'HDFC0001234', 'account_holder_name': 'Velocity Creative Agency Pvt Ltd', 'credits': [250000, 180000, 320000]},
    {'id': '22222222-2222-4222-8222-222222222222', 'name': 'Priya Sharma - Freelance Dev', 'email': 'priya@psd.in', 'account_number': '9876543210', 'ifsc_code': 'ICIC0009876', 'account_holder_name': 'Priya Sharma', 'credits': [75000, 50000, 90000]},
    {'id': '33333333-3333-4333-8333-333333333333', 'name': 'InvoiceZen SaaS', 'email': 'finance@invoicezen.io', 'account_number': '1122334455', 'ifsc_code': 'SBIN0011223', 'account_holder_name': 'InvoiceZen Technologies Pvt Ltd', 'credits': [1200000, 890000, 450000]},
    {'id': '44444444-4444-4444-8444-444444444444', 'name': 'Northstar Games Studio', 'email': 'finance@northstargames.in', 'account_number': '445566778899', 'ifsc_code': 'KKBK0004455', 'account_holder_name': 'Northstar Games Studio LLP', 'credits': [300000, 225000, 175000]},
    {'id': '55555555-5555-4555-8555-555555555555', 'name': 'Aarav Retail Co', 'email': 'accounts@aaravretail.in', 'account_number': '556677889900', 'ifsc_code': 'UTIB0005566', 'account_holder_name': 'Aarav Retail Co', 'credits': [150000, 125000, 98000]},
    {'id': '66666666-6666-4666-8666-666666666666', 'name': 'BluePeak Analytics', 'email': 'billing@bluepeak.io', 'account_number': '667788990011', 'ifsc_code': 'YESB0006677', 'account_holder_name': 'BluePeak Analytics Pvt Ltd', 'credits': [640000, 510000, 305000]},
    {'id': '77777777-7777-4777-8777-777777777777', 'name': 'Meera Design Lab', 'email': 'meera@designlab.in', 'account_number': '778899001122', 'ifsc_code': 'PUNB0007788', 'account_holder_name': 'Meera Design Lab', 'credits': [88000, 115000, 132000]},
    {'id': '88888888-8888-4888-8888-888888888888', 'name': 'CloudKart Marketplace', 'email': 'settlements@cloudkart.in', 'account_number': '889900112233', 'ifsc_code': 'CNRB0008899', 'account_holder_name': 'CloudKart Marketplace Pvt Ltd', 'credits': [980000, 760000, 620000]},
    {'id': '99999999-9999-4999-8999-999999999999', 'name': 'Sundial Tutors', 'email': 'admin@sundialtutors.in', 'account_number': '990011223344', 'ifsc_code': 'BARB0009900', 'account_holder_name': 'Sundial Tutors', 'credits': [125000, 87000, 66000]},
    {'id': 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'name': 'Zenith Logistics', 'email': 'payables@zenithlogistics.in', 'account_number': '101112131415', 'ifsc_code': 'IDFB0010111', 'account_holder_name': 'Zenith Logistics Pvt Ltd', 'credits': [430000, 390000, 270000]},
]

PAYOUT_PLANS = [
    (Payout.COMPLETED, 45000),
    (Payout.PENDING, 30000),
    (Payout.PROCESSING, 25000),
    (Payout.FAILED, 20000),
]


def payout_response(payout):
    return {
        'id': str(payout.id),
        'merchant': str(payout.merchant_id),
        'bank_account': str(payout.bank_account_id),
        'amount_paise': payout.amount_paise,
        'status': payout.status,
        'attempt_count': payout.attempt_count,
        'idempotency_key': payout.idempotency_key,
        'failure_reason': payout.failure_reason,
        'created_at': payout.created_at.isoformat(),
        'updated_at': payout.updated_at.isoformat(),
        'processing_started_at': payout.processing_started_at.isoformat() if payout.processing_started_at else None,
        'bank_account_last4': payout.bank_account.account_number[-4:],
    }


IdempotencyKey.objects.all().delete()
Payout.objects.all().delete()
LedgerEntry.objects.all().delete()
BankAccount.objects.all().delete()
Merchant.objects.all().delete()

for index, data in enumerate(MERCHANTS, start=1):
    merchant = Merchant.objects.create(id=uuid.UUID(data['id']), name=data['name'], email=data['email'])
    bank_account = BankAccount.objects.create(
        merchant=merchant,
        account_number=data['account_number'],
        ifsc_code=data['ifsc_code'],
        account_holder_name=data['account_holder_name'],
        is_primary=True,
    )

    for credit_index, amount in enumerate(data['credits'], start=1):
        LedgerEntry.objects.create(
            merchant=merchant,
            entry_type=LedgerEntry.CREDIT,
            amount_paise=amount,
            description=f'Demo credit {credit_index} for {merchant.name}',
        )

    for payout_index, (status, amount) in enumerate(PAYOUT_PLANS, start=1):
        payout_id = uuid.UUID(f'{index:08d}-{payout_index:04d}-4{index:03d}-8{payout_index:03d}-{index:012d}')
        idem_key = str(uuid.UUID(f'{index:08d}-{payout_index:04d}-4{payout_index:03d}-9{index:03d}-{payout_index:012d}'))
        processing_started_at = timezone.now() - timedelta(seconds=45) if status == Payout.PROCESSING else None
        attempt_count = 1 if status in [Payout.PROCESSING, Payout.COMPLETED, Payout.FAILED] else 0
        failure_reason = 'Bank rejected: demo beneficiary details mismatch' if status == Payout.FAILED else ''

        payout = Payout.objects.create(
            id=payout_id,
            merchant=merchant,
            bank_account=bank_account,
            amount_paise=amount,
            status=status,
            attempt_count=attempt_count,
            idempotency_key=idem_key,
            failure_reason=failure_reason,
            processing_started_at=processing_started_at,
        )

        LedgerEntry.objects.create(
            merchant=merchant,
            entry_type=LedgerEntry.DEBIT,
            amount_paise=amount,
            description=f'Demo payout hold: {payout.id}',
            reference_id=payout.id,
        )

        if status == Payout.FAILED:
            LedgerEntry.objects.create(
                merchant=merchant,
                entry_type=LedgerEntry.CREDIT,
                amount_paise=amount,
                description=f'Demo refund for failed payout {payout.id}: {failure_reason}',
                reference_id=payout.id,
            )

        IdempotencyKey.objects.create(
            merchant=merchant,
            key=idem_key,
            request_hash='seeded-demo-request',
            response_body=payout_response(payout),
            response_status=201,
            payout=payout,
            expires_at=timezone.now() + timedelta(hours=24),
        )

print('Seed complete.')
print(f'  Merchants: {Merchant.objects.count()}')
print(f'  Bank accounts: {BankAccount.objects.count()}')
print(f'  Ledger entries: {LedgerEntry.objects.count()}')
print(f'  Payouts: {Payout.objects.count()}')
print(f'  Idempotency keys: {IdempotencyKey.objects.count()}')

for merchant in Merchant.objects.all():
    print(
        f'  {merchant.id} | {merchant.name}: '
        f'total INR {merchant.get_balance() / 100:.2f}, '
        f'held INR {merchant.get_held_balance() / 100:.2f}, '
        f'available INR {merchant.get_available_balance() / 100:.2f}'
    )
''')
