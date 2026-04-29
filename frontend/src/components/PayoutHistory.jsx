const STATUS_COLORS = {
  pending:    'bg-yellow-100 text-yellow-800',
  processing: 'bg-blue-100 text-blue-800',
  completed:  'bg-green-100 text-green-800',
  failed:     'bg-red-100 text-red-800',
};

export default function PayoutHistory({ payouts }) {
  return (
    <div className="bg-white rounded-xl border p-6">
      <h2 className="text-sm font-medium text-gray-500 mb-4">Payout History</h2>
      <div className="overflow-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-gray-400 border-b">
              <th className="pb-2">Amount</th>
              <th className="pb-2">Status</th>
              <th className="pb-2">Date</th>
            </tr>
          </thead>
          <tbody>
            {payouts.length === 0 && (
              <tr><td colSpan={3} className="py-4 text-gray-400 text-center">No payouts yet</td></tr>
            )}
            {payouts.map(p => (
              <tr key={p.id} className="border-b last:border-0">
                <td className="py-2 font-medium">₹{(p.amount_paise / 100).toFixed(2)}</td>
                <td className="py-2">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[p.status]}`}>
                    {p.status}
                  </span>
                </td>
                <td className="py-2 text-gray-400">
                  {new Date(p.created_at).toLocaleDateString('en-IN')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
