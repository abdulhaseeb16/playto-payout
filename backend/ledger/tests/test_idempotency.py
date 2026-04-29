import uuid, json
from django.test import TestCase, Client
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

    def test_different_keys_create_different_payouts(self):
        r1 = self._post_payout(key=str(uuid.uuid4()))
        r2 = self._post_payout(key=str(uuid.uuid4()))
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        self.assertNotEqual(r1.json()['id'], r2.json()['id'])
        self.assertEqual(Payout.objects.filter(merchant=self.merchant).count(), 2)

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
        PayoutStateMachine.transition(payout_id, Payout.PROCESSING)
        PayoutStateMachine.transition(payout_id, Payout.COMPLETED)
        with self.assertRaises(InvalidTransitionError):
            PayoutStateMachine.transition(payout_id, Payout.PENDING)
