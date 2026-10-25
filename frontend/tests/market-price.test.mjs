import { JSDOM } from 'jsdom';
import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import React from 'react';
import fs from 'node:fs';

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost' });
Object.defineProperty(globalThis, 'window', { value: dom.window, configurable: true });
Object.defineProperty(globalThis, 'document', { value: dom.window.document, configurable: true });
Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true });
const { render, cleanup, waitFor } = await import('@testing-library/react');
const { default: MarketPricePanel } = await import('../components/MarketPricePanel');
const originalFetch = globalThis.fetch;
afterEach(() => { cleanup(); globalThis.fetch = originalFetch; });

const tokenProvider = async () => 'test-session';
const price = {
    symbol: 'AAPL', status: 'fresh', expected_trade_date: '2026-10-23',
    price: { source: 'massive', trade_date: '2026-10-23', open: '100', high: '110', low: '95',
        close: '105', volume: '51859042.576473', adjusted: true, fetched_at: '2026-10-24T08:00:00+00:00', version: 'test-version' },
};

test('authenticated user sees OHLCV, date, source and freshness from the API', async () => {
    globalThis.fetch = async (url, options) => {
        assert.equal(url, '/api/market-data/AAPL');
        assert.equal(new Headers(options?.headers).get('Authorization'), 'Bearer test-session');
        return new Response(JSON.stringify(price), { status: 200 });
    };
    const view = render(React.createElement(MarketPricePanel, { tokenProvider, enabled: true }));
    await waitFor(() => assert.match(view.container.textContent || '', /2026-10-23/));
    for (const text of ['AAPL', 'Massive', 'Fresh', '$105.00', '$100.00', '$110.00', '$95.00', '51,859,042.576473', 'Split-adjusted']) {
        assert.ok(view.container.textContent?.includes(text), `Missing visible field: ${text}`);
    }
});

test('stale data keeps its dated price and displays the expected trading date', async () => {
    globalThis.fetch = async () => new Response(JSON.stringify({ ...price, status: 'stale', expected_trade_date: '2026-10-26' }));
    const view = render(React.createElement(MarketPricePanel, { tokenProvider, enabled: true }));
    await waitFor(() => assert.match(view.container.textContent || '', /Stale/));
    assert.match(view.container.textContent || '', /2026-10-23/);
    assert.match(view.container.textContent || '', /2026-10-26/);
    assert.match(view.container.textContent || '', /\$105\.00/);
});

test('missing data displays unavailable and never a synthetic or zero price', async () => {
    globalThis.fetch = async () => new Response(JSON.stringify({ ...price, status: 'unavailable', price: null }));
    const view = render(React.createElement(MarketPricePanel, { tokenProvider, enabled: true }));
    await waitFor(() => assert.match(view.container.textContent || '', /No verified daily price/));
    assert.doesNotMatch(view.container.textContent || '', /\$/);
});

test('API errors and missing sessions never look like a valid quote', async () => {
    globalThis.fetch = async () => new Response('{"detail":"Unavailable"}', { status: 503 });
    const view = render(React.createElement(MarketPricePanel, { tokenProvider, enabled: true }));
    await waitFor(() => assert.ok(view.queryByRole('alert')));
    assert.doesNotMatch(view.container.textContent || '', /\$/);
});

test('signed-out panel never requests market data', async () => {
    let requests = 0;
    globalThis.fetch = async () => { requests++; return new Response('{}'); };
    render(React.createElement(MarketPricePanel, { tokenProvider, enabled: false }));
    assert.equal(requests, 0);
});

if (process.env.MARKET_LIVE_RESPONSE_FILE) {
    test('live-ingested API response renders its date, source and exact volume', async () => {
        const live = JSON.parse(fs.readFileSync(process.env.MARKET_LIVE_RESPONSE_FILE, 'utf8'));
        assert.equal(live.status, 'fresh');
        assert.equal(live.price.source, 'massive');
        globalThis.fetch = async () => new Response(JSON.stringify(live));
        const view = render(React.createElement(MarketPricePanel, { tokenProvider, enabled: true }));
        await waitFor(() => assert.ok(view.container.textContent.includes(live.price.trade_date)));
        assert.match(view.container.textContent || '', /Massive/);
        assert.ok(view.container.textContent.replaceAll(',', '').includes(live.price.volume));
    });
}
