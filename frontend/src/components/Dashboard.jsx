import { useCallback, useEffect, useState } from 'react';
import { getApiIndex, getDashboard } from '../api/client';
import BalanceCard from './BalanceCard';
import LedgerHistory from './LedgerHistory';
import PayoutForm from './PayoutForm';
import PayoutHistory from './PayoutHistory';

const FALLBACK_MERCHANTS = [
  { id: '11111111-1111-4111-8111-111111111111', name: 'Velocity Creative Agency' },
  { id: '22222222-2222-4222-8222-222222222222', name: 'Priya Sharma - Freelance Dev' },
  { id: '33333333-3333-4333-8333-333333333333', name: 'InvoiceZen SaaS' },
];

export default function Dashboard() {
  const [merchants, setMerchants] = useState(FALLBACK_MERCHANTS);
  const [activeMerchant, setActiveMerchant] = useState(FALLBACK_MERCHANTS[0].id);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let mounted = true;

    async function loadMerchants() {
      try {
        const res = await getApiIndex();
        const seededMerchants = res.data.seeded_merchants || [];
        if (mounted && seededMerchants.length > 0) {
          setMerchants(seededMerchants);
          setActiveMerchant((current) => (
            seededMerchants.some((merchant) => merchant.id === current)
              ? current
              : seededMerchants[0].id
          ));
        }
      } catch {
        if (mounted) {
          setMerchants(FALLBACK_MERCHANTS);
        }
      }
    }

    loadMerchants();
    return () => {
      mounted = false;
    };
  }, []);

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

  useEffect(() => {
    setLoading(true);
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading) return <div className="p-8 text-gray-500">Loading...</div>;
  if (error) return <div className="p-8 text-red-500">{error}</div>;

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b px-6 py-4 flex items-center gap-4">
        <h1 className="text-xl font-bold text-gray-900">Playto Pay</h1>
        <select
          value={activeMerchant}
          onChange={(e) => setActiveMerchant(e.target.value)}
          className="ml-auto border rounded px-3 py-1.5 text-sm"
        >
          {merchants.map((merchant) => (
            <option key={merchant.id} value={merchant.id}>
              {merchant.name}
            </option>
          ))}
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
        <LedgerHistory entries={data.ledger_entries || []} />
      </main>
    </div>
  );
}
