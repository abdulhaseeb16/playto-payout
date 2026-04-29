import threading, uuid, json
from django.test import TransactionTestCase
# IMPORTANT: Use TransactionTestCase NOT TestCase.
# TestCase wraps everything in a savepoint that never commits to the real DB.
# SELECT FOR UPDATE cannot be properly tested inside TestCase savepoints.
# TransactionTestCase flushes the DB between tests using real commits.
from ledger.models import Merchant, BankAccount, LedgerEntry, Payout


class ConcurrentPayoutTest(TransactionTestCase):
    """
    Two simultaneous 6000 paise (60 rupee) payout requests on a 10000 paise
    (100 rupee) balance. Exactly one should succeed (201), one fail (422).
    """

    def setUp(self):
        self.merchant = Merchant.objects.create(name="Test Merchant", email="test@example.com")
        self.bank = BankAccount.objects.create(
            merchant=self.merchant, account_number="1234567890",
            ifsc_code="HDFC0001234", account_holder_name="Test Merchant", is_primary=True,
        )
        LedgerEntry.objects.create(
            merchant=self.merchant, entry_type=LedgerEntry.CREDIT,
            amount_paise=10000, description="Test funding",
        )

    def _attempt_payout(self, amount_paise, results, index):
        from django.test import Client
        client = Client()
        response = client.post(
            f'/api/v1/merchants/{self.merchant.id}/payouts/',
            data=json.dumps({'amount_paise': amount_paise, 'bank_account_id': str(self.bank.id)}),
            content_type='application/json',
            headers={'Idempotency-Key': str(uuid.uuid4())},
        )
        results[index] = (response.status_code, response.json())

    def test_concurrent_overdraw_rejected(self):
        results = [None, None]
        threads = [
            threading.Thread(target=self._attempt_payout, args=(6000, results, 0)),
            threading.Thread(target=self._attempt_payout, args=(6000, results, 1)),
        ]
        for t in threads: t.start()
        for t in threads: t.join()

        status_codes = [r[0] for r in results]
        self.assertIn(201, status_codes, "One payout must succeed")
        self.assertIn(422, status_codes, "One payout must be rejected for insufficient funds")
        self.assertEqual(Payout.objects.filter(merchant=self.merchant).count(), 1)
        self.assertGreaterEqual(self.merchant.get_available_balance(), 0)
