import { useEffect, useState } from 'react';

import { getHealth } from '../api/client';
import BalanceCard from './BalanceCard';
import PayoutForm from './PayoutForm';
import PayoutHistory from './PayoutHistory';

export default function Dashboard() {
  const [apiStatus, setApiStatus] = useState('checking');

  useEffect(() => {
    getHealth()
      .then((data) => setApiStatus(data.status))
      .catch(() => setApiStatus('offline'));
  }, []);

  return (
    <main className="shell">
      <section className="toolbar">
        <div>
          <p className="eyebrow">Playto Pay</p>
          <h1>Payout Operations</h1>
        </div>
        <span className={`status status-${apiStatus}`}>{apiStatus}</span>
      </section>
      <BalanceCard />
      <section className="grid">
        <PayoutForm />
        <PayoutHistory />
      </section>
    </main>
  );
}
