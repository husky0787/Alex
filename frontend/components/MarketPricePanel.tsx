import React, { useEffect, useState } from 'react';
import { API_URL } from '../lib/config';

interface DailyPrice {
  source: string;
  trade_date: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
  adjusted: boolean;
  fetched_at: string;
  version: string;
}

interface MarketResult {
  symbol: string;
  status: 'fresh' | 'stale' | 'unavailable';
  expected_trade_date: string;
  price: DailyPrice | null;
}

interface Props {
  tokenProvider: () => Promise<string | null>;
  enabled: boolean;
}

const dollars = new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 4,
});

export default function MarketPricePanel({ tokenProvider, enabled }: Props) {
  const [data, setData] = useState<MarketResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!enabled) {
      setData(null);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(false);
    async function load() {
      try {
        const token = await tokenProvider();
        if (!token) throw new Error('Sign in required');
        const response = await fetch(`${API_URL}/api/market-data/AAPL`, {
          headers: { Authorization: `Bearer ${token}` }, signal: controller.signal,
        });
        if (!response.ok) throw new Error('Market data request failed');
        const result: MarketResult = await response.json();
        if (!controller.signal.aborted) setData(result);
      } catch {
        if (!controller.signal.aborted) { setError(true); setData(null); }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void load();
    return () => controller.abort();
  }, [enabled, tokenProvider]);

  if (loading) return <p role="status" className="text-gray-600 py-8">Loading verified market data…</p>;
  if (error) return <div role="alert" className="rounded-xl bg-amber-50 border border-amber-200 p-6">
    <h2 className="font-semibold">Market data unavailable</h2>
    <p className="mt-2 text-sm">Unable to load verified market data. Try again later.</p>
  </div>;
  if (!data?.price || data.status === 'unavailable') return <div role="status" className="rounded-xl bg-white border p-6">
    <h2 className="font-semibold">AAPL · Unavailable</h2>
    <p className="mt-2 text-sm text-gray-600">No verified daily price is available.</p>
    {data && <p className="mt-2 text-sm text-gray-600">Expected trading date: {data.expected_trade_date}</p>}
  </div>;

  const price = data.price;
  // Preserve fractional shares without a floating-point round trip.
  const [wholeVolume, fractionalVolume] = price.volume.split('.');
  const groupedVolume = wholeVolume.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  const volume = fractionalVolume ? `${groupedVolume}.${fractionalVolume}` : groupedVolume;
  return <section aria-label="Verified AAPL daily price" className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm">
    <div className="flex items-center justify-between gap-4 flex-wrap">
      <div>
        <h2 className="text-2xl font-semibold text-gray-900">AAPL</h2>
        <p className="text-sm text-gray-600 mt-1">Apple · Daily OHLCV · USD</p>
      </div>
      <span className={`rounded-full px-3 py-1 text-sm font-medium ${data.status === 'fresh' ? 'bg-green-50 text-green-800' : 'bg-amber-50 text-amber-900'}`}>
        {data.status === 'fresh' ? 'Fresh' : 'Stale'}
      </span>
    </div>
    <p className="mt-5 text-sm text-gray-700">Trading date: <strong>{price.trade_date}</strong> · Source: {price.source === 'massive' ? 'Massive' : price.source}</p>
    {data.status === 'stale' && <p role="status" className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
      This price is older than the expected trading date ({data.expected_trade_date}).
    </p>}
    <dl className="mt-6 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-5">
      {(['open', 'high', 'low', 'close'] as const).map(field => <div key={field}>
        <dt className="text-sm text-gray-500 capitalize">{field}</dt>
        <dd className="text-xl font-semibold text-gray-900 mt-1">{dollars.format(Number(price[field]))}</dd>
      </div>)}
      <div className="col-span-2 sm:col-span-1"><dt className="text-sm text-gray-500">Volume</dt><dd className="text-lg font-semibold text-gray-900 mt-1 break-words">{volume}</dd></div>
    </dl>
    <div className="mt-6 border-t pt-4 text-xs text-gray-500 space-y-1">
      <p>{price.adjusted ? 'Split-adjusted' : 'Unadjusted'} · End-of-day data, not a live quote.</p>
      <p>Retrieved: {price.fetched_at}</p>
    </div>
  </section>;
}
