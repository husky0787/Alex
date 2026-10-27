import { JSDOM } from 'jsdom';
import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import React from 'react';

const dom = new JSDOM('<!doctype html><html><body></body></html>');
for (const key of ['window', 'document', 'navigator']) {
  Object.defineProperty(globalThis, key, { value: key === 'window' ? dom.window : dom.window[key], configurable: true });
}
const { render, cleanup } = await import('@testing-library/react');
afterEach(cleanup);

test('report shows frozen prices and actual/expected dates with a stale warning', async () => {
  const { default: AnalysisPriceBasis } = await import('../components/AnalysisPriceBasis');
  const view = render(React.createElement(AnalysisPriceBasis, { snapshot: {
    captured_at: '2026-10-27T12:00:00+00:00', expected_trade_date: '2026-10-26', status: 'stale',
    prices: [{ symbol: 'AAPL', close: '105.123456789', trade_date: '2026-10-23', status: 'stale', source: 'massive' }],
  }}));
  assert.match(view.getByRole('alert').textContent, /Stale/);
  for (const text of ['2026-10-26', '2026-10-23', '105.123456789', 'AAPL', 'massive', 'USD']) {
    assert.ok(view.container.textContent.includes(text));
  }
});

test('legacy report is not labelled verified and fresh cash-only report invents no prices', async () => {
  const { default: AnalysisPriceBasis } = await import('../components/AnalysisPriceBasis');
  const view = render(React.createElement(AnalysisPriceBasis, {}));
  assert.match(view.container.textContent, /No verified price snapshot/);
  view.rerender(React.createElement(AnalysisPriceBasis, { snapshot: {
    captured_at: '2026-10-27T12:00:00+00:00', expected_trade_date: '2026-10-26', status: 'fresh', prices: [],
  }}));
  assert.match(view.container.textContent, /Cash-only/);
  assert.equal(view.queryByRole('alert'), null);
  assert.equal(view.queryByRole('table'), null);
});
