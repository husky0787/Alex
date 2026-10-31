import { JSDOM } from 'jsdom';
import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import Module, { createRequire } from 'node:module';
import React from 'react';

const load = createRequire(import.meta.url);
// tsx preserves this Next.js page's classic JSX; Next normally supplies its
// automatic JSX runtime. Only the test harness needs the global binding.
globalThis.React = React;

const dom = new JSDOM('<!doctype html><html><body></body></html>');
for (const key of ['window', 'document', 'navigator']) {
  Object.defineProperty(globalThis, key, { value: key === 'window' ? dom.window : dom.window[key], configurable: true });
}
const { render, cleanup, act, waitFor } = await import('@testing-library/react');
let auth;
const passThrough = ({ children }) => React.createElement(React.Fragment, null, children);
const originalLoad = Module._load;
Module._load = function (name, ...args) {
  if (name === '@clerk/nextjs') return { useAuth: () => auth };
  if (name === '../components/Layout' || name === 'next/head') return { __esModule: true, default: passThrough };
  if (name === 'recharts') return new Proxy({}, { get: () => () => null });
  if (name === '../components/Toast') return { showToast: () => {} };
  return originalLoad.call(this, name, ...args);
};
let Dashboard;
try {
  Dashboard = load('../pages/dashboard.tsx').default;
} finally {
  Module._load = originalLoad;
}
const originalFetch = globalThis.fetch;
afterEach(() => { cleanup(); globalThis.fetch = originalFetch; });

function healthy(url) {
  const data = url.endsWith('/api/user') ? { user: { display_name: 'Sample user' } }
    : url.endsWith('/api/accounts') ? [] : { jobs: [] };
  return Promise.resolve(new Response(JSON.stringify(data), { status: 200 }));
}

test('dashboard waits for Clerk to load and sign in before synchronizing', async () => {
  let requests = 0;
  auth = { isLoaded: false, isSignedIn: undefined, getToken: async () => 'test-only' };
  globalThis.fetch = async () => { requests++; return new Response('{}', { status: 403 }); };
  const view = render(React.createElement(Dashboard));
  await act(async () => {});
  assert.equal(requests, 0, 'unsettled authentication must not produce Failed to sync user: 403');
  auth = { ...auth, isLoaded: true, isSignedIn: false };
  view.rerender(React.createElement(Dashboard));
  await act(async () => {});
  assert.equal(requests, 0);
});

test('a successful new session clears an earlier sync 403', async () => {
  auth = { isLoaded: true, isSignedIn: true, getToken: async () => 'rejected-test-token' };
  globalThis.fetch = async () => new Response('{}', { status: 403 });
  const view = render(React.createElement(Dashboard));
  await view.findByText('Failed to sync user: 403');
  globalThis.fetch = healthy;
  auth = { ...auth, getToken: async () => 'new-test-token' };
  view.rerender(React.createElement(Dashboard));
  await view.findByDisplayValue('Sample user');
  await waitFor(() => assert.equal(Boolean(view.queryByText('Failed to sync user: 403')), false));
});

test('a late 403 from an obsolete session cannot replace a successful session', async () => {
  let rejectOldRequest;
  const pending = new Promise(resolve => { rejectOldRequest = resolve; });
  auth = { isLoaded: true, isSignedIn: true, getToken: async () => 'old-test-token' };
  let started = false;
  globalThis.fetch = async () => { started = true; return pending; };
  const view = render(React.createElement(Dashboard));
  await waitFor(() => assert.equal(started, true));
  globalThis.fetch = healthy;
  auth = { ...auth, getToken: async () => 'new-test-token' };
  view.rerender(React.createElement(Dashboard));
  await view.findByDisplayValue('Sample user');
  await act(async () => rejectOldRequest(new Response('{}', { status: 403 })));
  assert.equal(Boolean(view.queryByText('Failed to sync user: 403')), false);
});
