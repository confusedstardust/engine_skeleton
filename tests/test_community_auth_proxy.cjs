// Run: node tests/test_community_auth_proxy.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('../forge_frontend_next/node_modules/typescript');
const { NextRequest } = require('../forge_frontend_next/node_modules/next/server');
const filename = path.resolve(__dirname, '../forge_frontend_next/app/api/account/[...path]/route.ts');
const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const route = new Module(filename, module);
route.paths = Module._nodeModulePaths(path.dirname(filename));
route._compile(compiled, filename);
const originalFetch = global.fetch;
const originalOrigin = process.env.FORGE_SSO_ORIGIN;
const request = (body = {}, action = true) => new NextRequest('http://127.0.0.1:3001/api/account/login', { method: 'POST', headers: { 'Content-Type': 'application/json', ...(action ? { 'X-Forge-Auth-Action': '1' } : {}) }, body: JSON.stringify(body) });
const params = path => ({ params: Promise.resolve({ path: path.split('/') }) });
(async () => {
  let calls = 0;
  process.env.FORGE_SSO_ORIGIN = 'https://sso.example';
  global.fetch = async (url, init) => {
    calls++;
    assert.equal(String(url), 'https://sso.example/api/auth/login');
    assert.deepEqual(JSON.parse(init.body), { email: 'test@example.com', password: 'test-value' });
    assert.equal(init.redirect, 'error');
    return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'Set-Cookie': 'nos_session=test-session; Path=/; HttpOnly; SameSite=Lax' } });
  };
  assert.equal((await route.exports.POST(request(), params('not-allowed'))).status, 404);
  assert.equal((await route.exports.POST(request({}, false), params('login'))).status, 403);
  assert.equal((await route.exports.POST(request({ payload: 'x'.repeat(17000) }), params('login'))).status, 413);
  assert.equal(calls, 0);
  const response = await route.exports.POST(request({ email: 'test@example.com', password: 'test-value' }), params('login'));
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { ok: true });
  assert(response.headers.get('set-cookie').includes('HttpOnly'));
  assert.equal(response.headers.get('cache-control'), 'no-store');
  global.fetch = async () => new Response(JSON.stringify({ error: 'Invalid credentials' }), { status: 401 });
  const rejected = await route.exports.POST(request(), params('login'));
  assert.equal(rejected.status, 401);
  assert.deepEqual(await rejected.json(), { error: 'Invalid credentials' });
  global.fetch = async () => { throw new Error('upstream unreachable'); };
  assert.equal((await route.exports.POST(request(), params('register'))).status, 503);
  console.log('PASS auth proxy: endpoint allowlist, action header, size bound, configured upstream, session cookie forwarding, upstream errors, connection failure');
})().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => {
  global.fetch = originalFetch;
  if (originalOrigin === undefined) delete process.env.FORGE_SSO_ORIGIN; else process.env.FORGE_SSO_ORIGIN = originalOrigin;
});
