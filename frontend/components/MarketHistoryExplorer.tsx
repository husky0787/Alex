import React, { useEffect, useState } from 'react';
import { API_URL } from '../lib/config';
import MarketPricePanel from './MarketPricePanel';

interface Props {
  tokenProvider: () => Promise<string | null>;
  enabled: boolean;
}

interface Price {
  open: string; high: string; low: string; close: string; volume: string;
}
interface HistoryDay {
  date: string;
  status: 'available' | 'missing' | 'weekend' | 'holiday' | 'not_published';
  price: Price | null;
}
interface History {
  symbol: string; from_date: string; to_date: string; expected_trade_date: string;
  expected_count: number; available_count: number; missing_dates: string[];
  coverage: 'complete' | 'partial' | 'unavailable' | 'not_due'; days: HistoryDay[];
}
interface SymbolInfo { symbol: string; name: string; kind: string }

const dollars = new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 4,
});
const labels = { available: 'Available', missing: 'Missing data', weekend: 'Weekend',
  holiday: 'Market holiday', not_published: 'Not yet published' };

function HistoryChart({ history }: { history: History }) {
  const values = history.days.flatMap(day => day.price ? [Number(day.price.close)] : []);
  if (!values.length) return <p className="py-8 text-gray-600">No verified closing prices in this window.</p>;
  const low = Math.min(...values), high = Math.max(...values);
  const padding = Math.max((high - low) * 0.08, 1);
  const bottom = low - padding, top = high + padding;
  const x = (index: number) => 86 + index * 680 / Math.max(history.days.length - 1, 1);
  const y = (value: number) => 216 - (value - bottom) * 184 / (top - bottom);
  const segments: string[][] = [[]];
  const points: { x: number; y: number; day: HistoryDay }[] = [];
  history.days.forEach((day, index) => {
    if (day.status === 'missing' || day.status === 'not_published') {
      if (segments[segments.length - 1].length) segments.push([]);
    } else if (day.status === 'available' && day.price) {
      const point = { x: x(index), y: y(Number(day.price.close)), day };
      points.push(point);
      segments[segments.length - 1].push(`${point.x},${point.y}`);
    }
  });
  return <svg viewBox="0 0 800 264" role="img"
    aria-label={`${history.symbol} daily closing prices in USD; gaps indicate missing or unpublished data`}
    className="w-full min-w-[360px]">
    <title>{history.symbol} closing prices</title>
    {[top, (top + bottom) / 2, bottom].map(value => <g key={value}>
      <line x1="86" x2="766" y1={y(value)} y2={y(value)} stroke="#e5e7eb" />
      <text x="78" y={y(value) + 4} textAnchor="end" fill="#4b5563" fontSize="12">{dollars.format(value)}</text>
    </g>)}
    {segments.filter(segment => segment.length > 1).map((segment, index) =>
      <polyline key={index} points={segment.join(' ')} fill="none" stroke="#2563eb" strokeWidth="2.5" />)}
    {points.map(point => <circle key={point.day.date} cx={point.x} cy={point.y} r="3" fill="#2563eb">
      <title>{point.day.date}: {dollars.format(Number(point.day.price!.close))}</title>
    </circle>)}
    <text x="86" y="248" fill="#4b5563" fontSize="12">{history.from_date}</text>
    <text x="766" y="248" textAnchor="end" fill="#4b5563" fontSize="12">{history.to_date}</text>
  </svg>;
}

function HistoryPanel({ symbol, enabled, tokenProvider }: Props & { symbol: string }) {
  const [history, setHistory] = useState<History | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    if (!enabled) return () => controller.abort();
    async function load() {
      try {
        const token = await tokenProvider();
        if (!token) throw new Error('Sign in required');
        const response = await fetch(`${API_URL}/api/market-data/${encodeURIComponent(symbol)}/history`, {
          headers: { Authorization: `Bearer ${token}` }, signal: controller.signal,
        });
        if (!response.ok) throw new Error('History unavailable');
        const result: History = await response.json();
        if (!controller.signal.aborted) setHistory({ ...result, days: [...result.days].sort((a, b) => a.date.localeCompare(b.date)) });
      } catch {
        if (!controller.signal.aborted) setError(true);
      }
    }
    void load();
    return () => controller.abort();
  }, [enabled, symbol, tokenProvider]);
  if (error) return <p role="alert" className="mt-8 rounded-xl bg-amber-50 p-5 text-amber-900">History is unavailable. Please try again later.</p>;
  if (!history) return <p role="status" className="mt-8 text-gray-600">Loading daily history…</p>;
  return <section aria-label={`${symbol} history`} className="mt-8 rounded-2xl border border-gray-200 bg-white p-4 sm:p-6">
    <h2 className="text-xl font-semibold text-gray-900">{symbol} · Daily history</h2>
    <p className="mt-2 text-sm text-gray-600">{history.from_date} to {history.to_date} · America/New_York</p>
    <p className="mt-2 text-sm text-gray-600">Massive · USD · Split-adjusted · End-of-day prices</p>
    <p className="mt-3 font-medium text-gray-800">{history.available_count} of {history.expected_count} expected trading days available</p>
    {history.missing_dates.length > 0 && <p role="status" className="mt-2 text-amber-800">
      {history.missing_dates.length} trading day(s) missing. Gaps are left empty; prices are not filled with zero.
    </p>}
    <div className="mt-5 overflow-x-auto"><HistoryChart history={history} /></div>
    <p className="text-xs text-gray-500">Lines connect across weekends and market holidays, but break at missing or unpublished trading days. Exact OHLCV values appear below.</p>
    <div className="mt-5 max-h-96 overflow-auto rounded-lg border border-gray-200">
      <table aria-label={`${symbol} daily history`} className="w-full text-sm text-left whitespace-nowrap">
        <thead className="sticky top-0 bg-gray-50 text-gray-700"><tr>
          {['Date', 'Status', 'Open', 'High', 'Low', 'Close', 'Volume'].map(label =>
            <th scope="col" key={label} className="px-3 py-3 font-medium">{label}</th>)}
        </tr></thead>
        <tbody>{history.days.map(day => <tr key={day.date} className="border-t border-gray-100">
          <th scope="row" className="px-3 py-2 font-normal">{day.date}</th>
          <td className={`px-3 py-2 ${day.status === 'missing' ? 'text-amber-800' : 'text-gray-600'}`}>{labels[day.status]}</td>
          {(['open', 'high', 'low', 'close', 'volume'] as const).map(field =>
            <td key={field} className="px-3 py-2 tabular-nums">{day.price ? day.price[field] : '—'}</td>)}
        </tr>)}</tbody>
      </table>
    </div>
  </section>;
}

export default function MarketHistoryExplorer({ tokenProvider, enabled }: Props) {
  const [symbols, setSymbols] = useState<SymbolInfo[]>([]);
  const [symbol, setSymbol] = useState('AAPL');
  const [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setSymbols([]); setError(false);
    if (!enabled) return () => controller.abort();
    async function load() {
      try {
        const token = await tokenProvider();
        if (!token) throw new Error('Sign in required');
        const response = await fetch(`${API_URL}/api/market-data/universe`, {
          headers: { Authorization: `Bearer ${token}` }, signal: controller.signal,
        });
        if (!response.ok) throw new Error('Universe unavailable');
        const result: { symbols: SymbolInfo[] } = await response.json();
        if (!controller.signal.aborted) setSymbols(result.symbols);
      } catch {
        if (!controller.signal.aborted) setError(true);
      }
    }
    void load();
    return () => controller.abort();
  }, [enabled, tokenProvider]);
  if (!enabled) return <p className="text-gray-600">Sign in to view market history.</p>;
  if (error) return <p role="alert" className="text-amber-800">Supported symbols are unavailable. Please try again later.</p>;
  if (!symbols.length) return <p role="status" className="text-gray-600">Loading supported symbols…</p>;
  return <>
    <div className="mb-6 flex flex-col sm:flex-row sm:items-end gap-4">
      <div><label htmlFor="market-symbol" className="block text-sm font-medium text-gray-700">Symbol</label>
        <select id="market-symbol" value={symbol} onChange={event => setSymbol(event.target.value)}
          className="mt-2 w-full sm:w-80 rounded-lg border border-gray-300 bg-white p-3 text-gray-900">
          {symbols.map(item => <option key={item.symbol} value={item.symbol}>{item.symbol} · {item.name}</option>)}
        </select>
      </div>
      <p className="text-sm text-gray-600 pb-3">{symbols.length} supported US stocks and ETFs · Last 90 calendar days</p>
    </div>
    <MarketPricePanel key={`price-${symbol}`} symbol={symbol} tokenProvider={tokenProvider} enabled={enabled} />
    <HistoryPanel key={`history-${symbol}`} symbol={symbol} tokenProvider={tokenProvider} enabled={enabled} />
  </>;
}
