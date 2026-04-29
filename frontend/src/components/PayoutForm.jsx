import { useState } from 'react';
import { createPayout } from '../api/client';

export default function PayoutForm({ merchantId, bankAccounts, onSuccess }) {
  const [amountInr, setAmountInr] = useState('');
  const [bankAccountId, setBankAccountId] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState(null);  // { type: 'error'|'success', text: string }

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setMessage(null);
    // Convert INR to paise as integer — display only conversion, not stored
    const amountPaise = Math.round(parseFloat(amountInr) * 100);
    if (!amountPaise || amountPaise <= 0) {
      setMessage({ type: 'error', text: 'Enter a valid amount' });
      setSubmitting(false);
      return;
    }
    try {
      await createPayout(merchantId, { amount_paise: amountPaise, bank_account_id: bankAccountId });
      setMessage({ type: 'success', text: 'Payout requested successfully!' });
      setAmountInr('');
      onSuccess();  // trigger dashboard refresh
    } catch (err) {
      const msg = err.response?.data?.error || 'Failed to request payout';
      setMessage({ type: 'error', text: msg });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="bg-white rounded-xl border p-6">
      <h2 className="text-sm font-medium text-gray-500 mb-4">Request Payout</h2>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="text-xs text-gray-500">Amount (₹)</label>
          <input type="number" step="0.01" min="1"
            value={amountInr} onChange={e => setAmountInr(e.target.value)}
            placeholder="Enter amount in rupees"
            className="mt-1 w-full border rounded px-3 py-2 text-sm" required
          />
        </div>
        <div>
          <label className="text-xs text-gray-500">Bank Account</label>
          <select value={bankAccountId} onChange={e => setBankAccountId(e.target.value)}
            className="mt-1 w-full border rounded px-3 py-2 text-sm" required>
            <option value="">Select account</option>
            {bankAccounts.map(ba => (
              <option key={ba.id} value={ba.id}>
                {ba.account_holder_name} — ****{ba.account_number.slice(-4)}
              </option>
            ))}
          </select>
        </div>
        {message && (
          <p className={`text-sm ${message.type === 'error' ? 'text-red-500' : 'text-green-600'}`}>
            {message.text}
          </p>
        )}
        <button type="submit" disabled={submitting}
          className="w-full bg-blue-600 text-white rounded py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
          {submitting ? 'Submitting...' : 'Request Payout'}
        </button>
      </form>
    </div>
  );
}
