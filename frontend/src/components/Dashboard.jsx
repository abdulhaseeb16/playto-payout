import { useState, useEffect, useCallback } from 'react';
import { getDashboard } from '../api/client';
import BalanceCard from './BalanceCard';
import PayoutForm from './PayoutForm';
import PayoutHistory from './PayoutHistory';

// Replace these IDs after running seed.py — check the printed UUIDs
const MERCHANTS = [
  { id: 'REPLACE_WITH_SEEDED_UUID_1', name: 'Velocity Creative Agency' },
  { id: 'REPLACE_WITH_SEEDED_UUID_2', name: 'Priya Sharma — Freelance Dev' },
  { id: 'REPLACE_WITH_SEEDED_UUID_3', name: 'InvoiceZen SaaS' },
];

export default function Dashboard() {
  const [activeMerchant, setActiveMerchant] = useState(MERCHANTS[0].id);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const res = await getDashboard(activeMerchant);
      setData(res.data);
      setError(null);
    } catch {
      setError('Failed to load dashboard');
    } finally {
      setLoading(false);
    }
  }, [activeMerchant]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Poll every 5 seconds for live payout status updates
  useEffect(() => {
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);   // cleanup on unmount
  }, [fetchData]);

  if (loading) return <div className="p-8 text-gray-500">Loading...</div>;
  if (error)   return <div className="p-8 text-red-500">{error}</div>;

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b px-6 py-4 flex items-center gap-4">
        <h1 className="text-xl font-bold text-gray-900">Playto Pay</h1>
        <select value={activeMerchant}
          onChange={e => { setActiveMerchant(e.target.value); setLoading(true); }}
          className="ml-auto border rounded px-3 py-1.5 text-sm">
          {MERCHANTS.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>
      </header>
      <main className="max-w-5xl mx-auto p-6 space-y-6">
        <BalanceCard balance={data.balance} />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <PayoutForm
            merchantId={activeMerchant}
            bankAccounts={data.merchant.bank_accounts || []}
            onSuccess={fetchData}
          />
          <PayoutHistory payouts={data.payouts} />
        </div>
      </main>
    </div>
  );
}
