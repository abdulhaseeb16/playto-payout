const paise_to_inr = (paise) =>
  `₹${(paise / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
// Note: division by 100 is display-only. Storage always stays in integer paise.

export default function BalanceCard({ balance }) {
  return (
    <div className="bg-white rounded-xl border p-6">
      <h2 className="text-sm font-medium text-gray-500 mb-4">Balance Overview</h2>
      <div className="grid grid-cols-3 gap-4">
        <div>
          <p className="text-xs text-gray-400">Total</p>
          <p className="text-2xl font-bold text-gray-900">{paise_to_inr(balance.total_paise)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Held</p>
          <p className="text-2xl font-bold text-amber-500">{paise_to_inr(balance.held_paise)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Available</p>
          <p className="text-2xl font-bold text-green-600">{paise_to_inr(balance.available_paise)}</p>
        </div>
      </div>
    </div>
  );
}
