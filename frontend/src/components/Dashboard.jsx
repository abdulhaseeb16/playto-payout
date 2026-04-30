import { useCallback, useEffect, useState } from 'react';
import { getApiIndex, getDashboard } from '../api/client';
import BalanceCard from './BalanceCard';
import LedgerHistory from './LedgerHistory';
import PayoutForm from './PayoutForm';
import PayoutHistory from './PayoutHistory';

export default function Dashboard() {
  const [merchants, setMerchants] = useState([]);
  const [activeMerchant, setActiveMerchant] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let mounted = true;

    async function loadMerchants() {
      try {
        const res = await getApiIndex();
        const seededMerchants = res.data.seeded_merchants || [];
        if (!mounted) return;

        setMerchants(seededMerchants);
        if (seededMerchants.length > 0) {
          setActiveMerchant(seededMerchants[0].id);
        } else {
          setError('No merchants found. Seed demo data on the backend first.');
          setLoading(false);
        }
      } catch {
        if (mounted) {
          setError('Failed to load API');
          setLoading(false);
        }
      }
    }

    loadMerchants();
    return () => {
      mounted = false;
    };
  }, []);

  const fetchData = useCallback(async () => {
    if (!activeMerchant) return;

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
