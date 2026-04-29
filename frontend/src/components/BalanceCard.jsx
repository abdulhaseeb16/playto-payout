export default function BalanceCard() {
  return (
    <section className="panel balance-panel">
      <div>
        <p className="label">Available balance</p>
        <strong>INR 0.00</strong>
      </div>
      <div>
        <p className="label">Held balance</p>
        <strong>INR 0.00</strong>
      </div>
      <div>
        <p className="label">Total balance</p>
        <strong>INR 0.00</strong>
      </div>
    </section>
  );
}
