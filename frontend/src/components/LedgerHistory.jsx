const TYPE_COLORS = {
  credit: 'text-green-700',
  debit: 'text-red-700',
};

const formatInr = (paise) => `INR ${(paise / 100).toFixed(2)}`;

export default function LedgerHistory({ entries }) {
  return (
    <div className="bg-white rounded-xl border p-6">
      <h2 className="text-sm font-medium text-gray-500 mb-4">Recent Ledger Entries</h2>
      <div className="overflow-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-gray-400 border-b">
              <th className="pb-2">Type</th>
              <th className="pb-2">Amount</th>
              <th className="pb-2">Description</th>
              <th className="pb-2">Date</th>
            </tr>
          </thead>
          <tbody>
            {entries.length === 0 && (
              <tr>
                <td colSpan={4} className="py-4 text-gray-400 text-center">
                  No ledger entries yet
                </td>
              </tr>
            )}
            {entries.map((entry) => (
              <tr key={entry.id} className="border-b last:border-0">
                <td className={`py-2 font-medium ${TYPE_COLORS[entry.type] || 'text-gray-700'}`}>
                  {entry.type}
                </td>
                <td className="py-2 font-medium">{formatInr(entry.amount_paise)}</td>
                <td className="py-2 text-gray-600">{entry.description}</td>
                <td className="py-2 text-gray-400">
                  {new Date(entry.created_at).toLocaleDateString('en-IN')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
