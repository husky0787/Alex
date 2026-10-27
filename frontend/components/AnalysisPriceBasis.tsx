import React from 'react';

export interface AnalysisSnapshot {
  captured_at: string;
  expected_trade_date: string;
  status: 'fresh' | 'stale';
  prices: { symbol: string; close: string; trade_date: string; status: 'fresh' | 'stale'; source: string }[];
}

export default function AnalysisPriceBasis({ snapshot }: { snapshot?: AnalysisSnapshot }) {
  if (!snapshot) return <p className="mb-8 rounded-lg bg-amber-50 p-5 text-amber-900">
    No verified price snapshot is available for this historical report.
  </p>;
  return <section aria-label="Analysis price basis" className="mb-8 rounded-lg bg-white p-6 shadow">
    <h2 className="text-xl font-semibold text-gray-900">Price basis</h2>
    <p className="mt-2 text-sm text-gray-600">Fixed at {snapshot.captured_at}. Expected published trading date: {snapshot.expected_trade_date}.</p>
    <p className="mt-2 text-sm text-gray-600">USD · Split-adjusted daily closes · Prices and holdings are fixed for this report.</p>
    {snapshot.status === 'stale' && <p role="alert" className="mt-3 rounded bg-amber-50 p-3 text-amber-900">
      Stale prices were used. Some holdings are valued using an earlier trading date, shown below.
    </p>}
    {snapshot.prices.length ? <div className="mt-4 overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead><tr>{['Symbol', 'Close (USD)', 'Trading date', 'Status', 'Source'].map(label =>
          <th key={label} scope="col" className="px-3 py-2">{label}</th>)}</tr></thead>
        <tbody>{snapshot.prices.map(price => <tr key={price.symbol} className="border-t border-gray-100">
          <th scope="row" className="px-3 py-2">{price.symbol}</th>
          <td className="px-3 py-2 tabular-nums">{price.close}</td>
          <td className="px-3 py-2">{price.trade_date}</td>
          <td className="px-3 py-2">{price.status}</td>
          <td className="px-3 py-2">{price.source}</td>
        </tr>)}</tbody>
      </table>
    </div> : <p className="mt-4 text-gray-600">Cash-only portfolio; no market prices required.</p>}
  </section>;
}
