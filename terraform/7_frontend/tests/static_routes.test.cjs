const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const context = vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../static_routes.js'), 'utf8'), context);

test('clean dashboard URL resolves to its exported HTML without a homepage fallback', () => {
    const request = { uri: '/dashboard', method: 'GET', querystring: {} };
    assert.equal(context.handler({ request }).uri, '/dashboard.html');
});

for (const [uri, expected] of [
    ['/', '/index.html'],
    ['/dashboard/', '/dashboard.html'],
    ['/accounts/', '/accounts.html'],
    ['/accounts/abc/', '/accounts/%5Bid%5D.html'],
    ['/missing-page', '/missing-page.html'],
    ['/api', '/api'],
    ['/api/accounts', '/api/accounts'],
    ['/_next/data/build/dashboard.json', '/_next/data/build/dashboard.json'],
    ['/_next/asset', '/_next/asset'],
    ['/favicon.ico', '/favicon.ico'],
    ['/accounts/[id].html', '/accounts/[id].html'],
]) {
    test(`GET ${uri} resolves to ${expected}`, () => {
        const request = { uri, method: 'GET', querystring: { source: { value: 'test' } } };
        const result = context.handler({ request });
        assert.equal(result.uri, expected);
        assert.equal(result.querystring.source.value, 'test');
    });
}

test('HEAD requests resolve HTML, while non-read requests are not rewritten', () => {
    assert.equal(context.handler({ request: { uri: '/dashboard', method: 'HEAD' } }).uri, '/dashboard.html');
    for (const method of ['POST', 'OPTIONS']) {
        assert.equal(context.handler({ request: { uri: '/dashboard', method } }).uri, '/dashboard');
    }
});

test('account deep links resolve to the dynamic exported page shell', () => {
    const request = { uri: '/accounts/123e4567-e89b-12d3-a456-426614174000', method: 'GET', querystring: {} };
    assert.equal(context.handler({ request }).uri, '/accounts/%5Bid%5D.html');
});
