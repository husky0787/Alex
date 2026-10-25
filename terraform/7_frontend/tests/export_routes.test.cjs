// Run after frontend's production build to verify real S3 object targets.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const context = vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../static_routes.js'), 'utf8'), context);
const exported = path.resolve(__dirname, '../../../frontend/out');

test('all public page routes resolve to actual production-exported HTML', () => {
    for (const uri of ['/', '/dashboard', '/accounts', '/analysis', '/advisor-team',
        '/accounts/123e4567-e89b-12d3-a456-426614174000']) {
        const result = context.handler({ request: { uri, method: 'GET' } });
        const file = path.join(exported, decodeURIComponent(result.uri.slice(1)));
        assert.ok(fs.existsSync(file), `${uri} has no exported target: ${file}; run npm run build first`);
        assert.match(fs.readFileSync(file, 'utf8'), /<html/);
    }
});

test('unknown pages do not resolve to an existing success-page object', () => {
    const result = context.handler({ request: { uri: '/not-a-real-page', method: 'GET' } });
    assert.equal(fs.existsSync(path.join(exported, result.uri.slice(1))), false);
});
