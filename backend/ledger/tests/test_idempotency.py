import uuid, json
from django.test import TestCase, Client
from unittest.mock import patch
from ledger.models import Merchant, BankAccount, LedgerEntry, Payout, IdempotencyKey


class IdempotencyTest(TestCase):

    def setUp(self):
        self.merchant = Merchant.objects.create(name="Idem Merchant", email="idem@example.com")
        self.bank = BankAccount.objects.create(
            merchant=self.merchant, account_number="0987654321",
            ifsc_code="ICIC0009876", account_holder_name="Idem Merchant", is_primary=True,
        )
        LedgerEntry.objects.create(
            merchant=self.merchant, entry_type=LedgerEntry.CREDIT,
            amount_paise=50000, description="Test funding",
        )
        self.client = Client()
        self.idempotency_key = str(uuid.uuid4())
        self.enqueue_patcher = patch('ledger.views.process_payout.apply_async')
        self.enqueue_patcher.start()

    def tearDown(self):
        self.enqueue_patcher.stop()

    def _post_payout(self, key=None, amount=5000):
        return self.client.post(
            f'/api/v1/merchants/{self.merchant.id}/payouts/',
            data=json.dumps({'amount_paise': amount, 'bank_account_id': str(self.bank.id)}),
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY=key or self.idempotency_key,
        )

    def test_same_key_returns_same_response(self):
        """Second call with same key returns identical response, creates no new payout."""
        r1 = self._post_payout()
        r2 = self._post_payout()
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        self.assertEqual(r1.json()['id'], r2.json()['id'])
        self.assertEqual(Payout.objects.filter(merchant=self.merchant).count(), 1)
        self.assertEqual(
            LedgerEntry.objects.filter(
                merchant=self.merchant,
                entry_type=LedgerEntry.DEBIT,
                reference_id=r1.json()['id'],
            ).count(),
            1,
        )

    def test_same_key_with_different_body_is_rejected(self):
        r1 = self._post_payout(amount=5000)
        r2 = self._post_payout(amount=6000)
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 409)
        self.assertEqual(Payout.objects.filter(merchant=self.merchant).count(), 1)

    def test_different_keys_create_different_payouts(self):
        r1 = self._post_payout(key=str(uuid.uuid4()))
        r2 = self._post_payout(key=str(uuid.uuid4()))
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        self.assertNotEqual(r1.json()['id'], r2.json()['id'])
        self.assertEqual(Payout.objects.filter(merchant=self.merchant).count(), 2)

    def test_flat_payout_endpoint_derives_merchant_from_bank_account(self):
        r = self.client.post(
            '/api/v1/payouts/',
            data=json.dumps({'amount_paise': 5000, 'bank_account_id': str(self.bank.id)}),
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()['merchant'], str(self.merchant.id))

    def test_keys_scoped_per_merchant(self):
        """Same key for two different merchants creates two separate payouts."""
        m2 = Merchant.objects.create(name="Second Merchant", email="m2@example.com")
        b2 = BankAccount.objects.create(
            merchant=m2, account_number="1111111111",
            ifsc_code="HDFC0000001", account_holder_name="Second Merchant", is_primary=True,
        )
        LedgerEntry.objects.create(merchant=m2, entry_type=LedgerEntry.CREDIT, amount_paise=50000, description="Funding")
        shared_key = str(uuid.uuid4())
        r1 = self._post_payout(key=shared_key)
        r2 = self.client.post(
            f'/api/v1/merchants/{m2.id}/payouts/',
            data=json.dumps({'amount_paise': 5000, 'bank_account_id': str(b2.id)}),
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY=shared_key,
        )
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        self.assertNotEqual(r1.json()['id'], r2.json()['id'])

    def test_missing_idempotency_key_rejected(self):
        r = self.client.post(
            f'/api/v1/merchants/{self.merchant.id}/payouts/',
            data=json.dumps({'amount_paise': 5000, 'bank_account_id': str(self.bank.id)}),
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 400)

    def test_state_machine_rejects_illegal_transition(self):
        from ledger.state_machine import PayoutStateMachine, InvalidTransitionError
        r = self._post_payout()
        payout_id = r.json()['id']
        self.assertEqual(
            LedgerEntry.objects.filter(reference_id=payout_id, entry_type=LedgerEntry.DEBIT).count(),
            1,
        )
        PayoutStateMachine.transition(payout_id, Payout.PROCESSING)
        PayoutStateMachine.transition(payout_id, Payout.COMPLETED)
        self.assertEqual(
            LedgerEntry.objects.filter(reference_id=payout_id, entry_type=LedgerEntry.DEBIT).count(),
            1,
        )
        self.assertEqual(
            LedgerEntry.objects.filter(reference_id=payout_id, entry_type=LedgerEntry.CREDIT).count(),
            0,
        )
        with self.assertRaises(InvalidTransitionError):
            PayoutStateMachine.transition(payout_id, Payout.PENDING)

    def test_state_machine_rejects_failed_to_completed(self):
        from ledger.state_machine import PayoutStateMachine, InvalidTransitionError
        r = self._post_payout()
        payout_id = r.json()['id']
        PayoutStateMachine.transition(payout_id, Payout.PROCESSING)
        PayoutStateMachine.transition(payout_id, Payout.FAILED, failure_reason='test failure')
        self.assertEqual(
            LedgerEntry.objects.filter(reference_id=payout_id, entry_type=LedgerEntry.DEBIT).count(),
            1,
        )
        self.assertEqual(
            LedgerEntry.objects.filter(reference_id=payout_id, entry_type=LedgerEntry.CREDIT).count(),
            1,
        )
        self.assertEqual(self.merchant.get_available_balance(), 50000)
        with self.assertRaises(InvalidTransitionError):
            PayoutStateMachine.transition(payout_id, Payout.COMPLETED)
