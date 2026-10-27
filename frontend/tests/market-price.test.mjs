import { JSDOM } from 'jsdom';
import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import React from 'react';
import fs from 'node:fs';

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost' });
Object.defineProperty(globalThis, 'window', { value: dom.window, configurable: true });
Object.defineProperty(globalThis, 'document', { value: dom.window.document, configurable: true });
Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true });
const { render, cleanup, waitFor, fireEvent } = await import('@testing-library/react');
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

test('history explorer switches symbol and shows sorted real bars with a visible missing-day gap', async () => {
    const { default: MarketHistoryExplorer } = await import('../components/MarketHistoryExplorer');
    const requested = [];
    globalThis.fetch = async (url, options) => {
        requested.push(url);
        assert.equal(new Headers(options?.headers).get('Authorization'), 'Bearer test-session');
        if (url.endsWith('/universe')) return new Response(JSON.stringify({
            source: 'massive', symbols: [{ symbol: 'AAPL', name: 'Apple', kind: 'stock' },
                { symbol: 'MSFT', name: 'Microsoft', kind: 'stock' }],
        }));
        const symbol = url.includes('/MSFT') ? 'MSFT' : 'AAPL';
        if (!url.endsWith('/history')) return new Response(JSON.stringify({ ...price, symbol }));
        return new Response(JSON.stringify({
            symbol, source: 'massive', from_date: '2026-10-20', to_date: '2026-10-26',
            expected_trade_date: '2026-10-23', expected_count: 4, available_count: 3,
            coverage: 'partial', missing_dates: ['2026-10-22'], adjusted: true,
            days: [
                { date: '2026-10-26', status: 'not_published', price: null },
                { date: '2026-10-25', status: 'weekend', price: null },
                { date: '2026-10-24', status: 'weekend', price: null },
                { date: '2026-10-23', status: 'available', price: price.price },
                { date: '2026-10-22', status: 'missing', price: null },
                { date: '2026-10-21', status: 'available', price: { ...price.price, trade_date: '2026-10-21' } },
                { date: '2026-10-20', status: 'available', price: { ...price.price, trade_date: '2026-10-20' } },
            ],
        }));
    };
    const view = render(React.createElement(MarketHistoryExplorer, { tokenProvider, enabled: true }));
    await waitFor(() => assert.ok(view.queryByRole('table', { name: 'AAPL daily history' })));
    const table = view.getByRole('table', { name: 'AAPL daily history' });
    assert.match(table.textContent, /Missing data/);
    assert.match(table.textContent, /Not yet published/);
    assert.match(table.textContent, /Weekend/);
    const dates = [...table.querySelectorAll('tbody tr')].map(row => row.cells[0].textContent);
    assert.equal(dates[0], '2026-10-20');
    assert.equal(dates.at(-1), '2026-10-26');
    const chart = view.getByRole('img', { name: /AAPL daily closing prices/ });
    assert.equal(chart.querySelectorAll('circle').length, 3);
    assert.equal(chart.querySelectorAll('polyline').length, 1); // no line spanning the missing session
    assert.doesNotMatch(table.textContent, /\$0\.00/);
    fireEvent.change(view.getByRole('combobox', { name: 'Symbol' }), { target: { value: 'MSFT' } });
    await waitFor(() => assert.ok(view.queryByRole('table', { name: 'MSFT daily history' })));
    assert.ok(requested.includes('/api/market-data/MSFT/history'));
    assert.ok(requested.includes('/api/market-data/MSFT'));
    await waitFor(() => assert.ok(view.queryByRole('region', { name: 'Verified MSFT daily price' })));
    assert.equal(view.queryByRole('table', { name: 'AAPL daily history' }), null);
});

test('history explorer shows empty history and errors without fabricating a chart', async () => {
    const { default: MarketHistoryExplorer } = await import('../components/MarketHistoryExplorer');
    let fail = false;
    globalThis.fetch = async url => {
        if (url.endsWith('/universe')) return new Response(JSON.stringify({ symbols: [{ symbol: 'AAPL', name: 'Apple' }] }));
        if (!url.endsWith('/history')) return new Response(JSON.stringify({ ...price, price: null, status: 'unavailable' }));
        if (fail) return new Response('{}', { status: 503 });
        return new Response(JSON.stringify({ symbol: 'AAPL', from_date: '2026-10-23', to_date: '2026-10-23',
            expected_count: 1, available_count: 0, coverage: 'unavailable', missing_dates: ['2026-10-23'],
            days: [{ date: '2026-10-23', status: 'missing', price: null }] }));
    };
    let view = render(React.createElement(MarketHistoryExplorer, { tokenProvider, enabled: true }));
    await waitFor(() => assert.match(view.container.textContent, /No verified closing prices/));
    assert.equal(view.queryByRole('img'), null);
    assert.doesNotMatch(view.container.textContent, /\$0\.00/);
    cleanup();
    fail = true;
    view = render(React.createElement(MarketHistoryExplorer, { tokenProvider, enabled: true }));
    await waitFor(() => assert.match(view.getByRole('alert').textContent, /History is unavailable/));
    assert.equal(view.queryByRole('table'), null);
});

test('history explorer ignores a slow previous-symbol response and makes no signed-out request', async () => {
    const { default: MarketHistoryExplorer } = await import('../components/MarketHistoryExplorer');
    let calls = 0, release;
    globalThis.fetch = async url => {
        calls++;
        if (url.endsWith('/universe')) return new Response(JSON.stringify({ symbols: [
            { symbol: 'AAPL', name: 'Apple' }, { symbol: 'MSFT', name: 'Microsoft' }] }));
        const symbol = url.includes('MSFT') ? 'MSFT' : 'AAPL';
        if (!url.endsWith('/history')) return new Response(JSON.stringify({ ...price, symbol }));
        const body = { symbol, from_date: '2026-10-23', to_date: '2026-10-23', expected_count: 1,
            available_count: 1, missing_dates: [], coverage: 'complete',
            days: [{ date: '2026-10-23', status: 'available', price: price.price }] };
        if (symbol === 'AAPL') await new Promise(resolve => { release = resolve; });
        return new Response(JSON.stringify(body));
    };
    const view = render(React.createElement(MarketHistoryExplorer, { tokenProvider, enabled: false }));
    assert.equal(calls, 0);
    view.rerender(React.createElement(MarketHistoryExplorer, { tokenProvider, enabled: true }));
    await waitFor(() => assert.equal(typeof release, 'function'));
    fireEvent.change(view.getByRole('combobox'), { target: { value: 'MSFT' } });
    await waitFor(() => assert.ok(view.queryByRole('table', { name: 'MSFT daily history' })));
    release();
    await new Promise(resolve => setTimeout(resolve, 30));
    assert.equal(view.queryByRole('table', { name: 'AAPL daily history' }), null);
    assert.ok(view.queryByRole('table', { name: 'MSFT daily history' }));
});

if (process.env.MARKET_LIVE_HISTORY_FILE) {
    test('live 20-symbol universe and AAPL history render actual verified bars', async () => {
        const { default: MarketHistoryExplorer } = await import('../components/MarketHistoryExplorer');
        const live = JSON.parse(fs.readFileSync(process.env.MARKET_LIVE_HISTORY_FILE, 'utf8'));
        globalThis.fetch = async url => new Response(JSON.stringify(url.endsWith('/universe') ? live.universe :
            url.endsWith('/history') ? live.histories.AAPL : live.latest));
        const view = render(React.createElement(MarketHistoryExplorer, { tokenProvider, enabled: true }));
        await waitFor(() => assert.ok(view.queryByRole('table', { name: 'AAPL daily history' })));
        assert.equal(view.getAllByRole('option').length, 20);
        assert.equal(view.getByRole('img').querySelectorAll('circle').length, live.histories.AAPL.available_count);
        const expected = live.histories.AAPL.days.filter(day => day.price).at(-1);
        assert.ok(view.getByRole('table').textContent.includes(expected.price.close));
        assert.ok(view.getByRole('table').textContent.includes(expected.price.volume));
    });
}

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
