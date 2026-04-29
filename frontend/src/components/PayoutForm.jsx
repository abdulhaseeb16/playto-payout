export default function PayoutForm() {
  return (
    <section className="panel">
      <h2>Request payout</h2>
      <form className="stack">
        <label>
          Amount
          <input type="number" min="1" step="0.01" placeholder="0.00" />
        </label>
        <label>
          Bank account
          <select defaultValue="">
            <option value="" disabled>
              Select an account
            </option>
          </select>
        </label>
        <button type="button">Create payout</button>
      </form>
    </section>
  );
}
