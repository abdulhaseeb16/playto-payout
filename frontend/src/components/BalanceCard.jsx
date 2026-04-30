const paiseToInr = (paise) =>
  `INR ${(paise / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;

export default function BalanceCard({ balance }) {
  return (
    <div className="bg-white rounded-xl border p-6">
      <h2 className="text-sm font-medium text-gray-500 mb-4">Balance Overview</h2>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div>
          <p className="text-xs text-gray-400">Total</p>
          <p className="text-2xl font-bold text-gray-900">{paiseToInr(balance.total_paise)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Held</p>
          <p className="text-2xl font-bold text-amber-500">{paiseToInr(balance.held_paise)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Available</p>
          <p className="text-2xl font-bold text-green-600">{paiseToInr(balance.available_paise)}</p>
        </div>
      </div>
    </div>
  );
}
