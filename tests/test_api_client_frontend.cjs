const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { loadFrontendTs } = require('./helpers/load_frontend_ts.cjs');
const filename = path.resolve(__dirname, '../forge_frontend_next/lib/api-client.ts');

function setup(t, respond) {
  const previous = { fetch: global.fetch, window: global.window, basePath: process.env.NEXT_PUBLIC_BASE_PATH };
  process.env.NEXT_PUBLIC_BASE_PATH = '/forge';
  global.window = { localStorage: { getItem: () => '中文邀请码' } };
  const calls = [];
  global.fetch = async (url, init) => { calls.push({ url, init }); return respond(url, init); };
  t.after(() => {
    global.fetch = previous.fetch;
    if (previous.window === undefined) delete global.window; else global.window = previous.window;
    if (previous.basePath === undefined) delete process.env.NEXT_PUBLIC_BASE_PATH; else process.env.NEXT_PUBLIC_BASE_PATH = previous.basePath;
  });
  return { ...loadFrontendTs(filename), calls };
}

test('JSON requests retain invitation, credentials, base path, caller Headers and AbortSignal', async t => {
  const { forgeApi, calls } = setup(t, () => Response.json({ ok: true }));
  const controller = new AbortController();
  assert.deepEqual(await forgeApi('/jobs', { method: 'POST', body: '{}', headers: new Headers({ 'X-Custom': 'value' }), signal: controller.signal }), { ok: true });
  const { url, init } = calls[0];
  assert.equal(url, '/forge/api/forge/jobs');
  assert.equal(init.credentials, 'include');
  assert.equal(init.cache, 'no-store');
  assert.equal(init.headers.get('X-WebGAL-Invite-Code'), encodeURIComponent('中文邀请码'));
  assert.equal(init.headers.get('X-Custom'), 'value');
  assert.equal(init.headers.get('Content-Type'), 'application/json');
  assert.equal(init.signal, controller.signal);
});

test('admin and community action headers survive header merging and tuple headers', async t => {
  const { adminApi, calls } = setup(t, () => Response.json({}));
  await adminApi('/users', { headers: [['X-Custom', 'tuple']] });
  assert.equal(calls[0].init.headers.get('X-Forge-Admin-Action'), '1');
  assert.equal(calls[0].init.headers.get('X-Custom'), 'tuple');
  const { boardApi } = loadFrontendTs(path.resolve(__dirname, '../forge_frontend_next/lib/community.ts'));
  await boardApi('/community', { method: 'POST', body: '{}' });
  assert.equal(calls[1].init.headers.get('X-Forge-Community-Action'), '1');
  assert.equal(calls[1].init.headers.get('X-Forge-Admin-Action'), '1');
});

test('FormData keeps the original body and lets fetch generate the multipart boundary', async t => {
  const { adminApi, calls } = setup(t, () => Response.json({}));
  const body = new FormData(); body.append('file', new Blob(['image']), 'figure.webp');
  await adminApi('/assets/upload', { method: 'POST', body, headers: { 'Content-Type': 'application/json' } });
  assert.equal(calls[0].init.body, body);
  assert.equal(calls[0].init.headers.has('Content-Type'), false);
  assert.equal(calls[0].init.headers.get('X-Forge-Admin-Action'), '1');
});

test('music preview returns bytes through the authenticated Blob path', async t => {
  const { forgeApi, calls } = setup(t, () => new Response('music', { headers: { 'Content-Type': 'audio/mpeg' } }));
  const blob = await forgeApi.blob('/jobs/job/music-library/music.mp3');
  assert.equal(await blob.text(), 'music');
  assert.equal(blob.type, 'audio/mpeg');
  assert.ok(calls[0].init.headers.has('X-WebGAL-Invite-Code'));
});

test('account authentication has its own prefix and action header without invitation leakage', async t => {
  const { accountApi, calls } = setup(t, () => Response.json({ cooldown: 60 }));
  await accountApi('/email/send-code', { method: 'POST', body: '{}' });
  assert.equal(calls[0].url, '/forge/api/account/email/send-code');
  assert.equal(calls[0].init.headers.get('X-Forge-Auth-Action'), '1');
  assert.equal(calls[0].init.headers.has('X-WebGAL-Invite-Code'), false);
});

test('payments retain request keys and order endpoint', async t => {
  const { paymentsApi, calls } = setup(t, () => Response.json({ id: 'order' }));
  const body = JSON.stringify({ request_key: 'retry-key' });
  await paymentsApi('/orders', { method: 'POST', body });
  assert.equal(calls[0].url, '/forge/api/forge/payments/orders');
  assert.equal(calls[0].init.body, body);
});

test('structured errors retain status, diagnostic context and validation messages', async t => {
  const { forgeApi, ApiError } = setup(t, () => Response.json({ detail: { message: '生成失败', operation: 'assets', provider: 'kimi', diagnostic_id: 'test-id' } }, { status: 503 }));
  await assert.rejects(forgeApi('/jobs'), e => e instanceof ApiError && e.status === 503 && /生成失败.*assets.*Kimi.*test-id/.test(e.message));
  global.fetch = async () => Response.json({ detail: [{ msg: '字段缺失' }, '参数错误'] }, { status: 422 });
  await assert.rejects(forgeApi('/jobs'), /字段缺失；参数错误/);
});

test('plain text, HTML and account errors produce readable messages', async t => {
  const { forgeApi, accountApi } = setup(t, () => new Response('服务繁忙', { status: 502 }));
  await assert.rejects(forgeApi('/jobs'), /服务繁忙/);
  global.fetch = async () => new Response('<html>upstream failure</html>', { status: 502 });
  await assert.rejects(forgeApi('/jobs'), e => /HTTP 502/.test(e.message) && !e.message.includes('<html>'));
  global.fetch = async () => Response.json({ error: '验证码错误' }, { status: 400 });
  await assert.rejects(accountApi('/login'), /验证码错误/);
});

test('204 succeeds, malformed success JSON fails, and cancellation is not wrapped', async t => {
  const { forgeApi } = setup(t, () => new Response(null, { status: 204 }));
  assert.equal(await forgeApi('/assets/asset', { method: 'DELETE' }), undefined);
  global.fetch = async () => new Response('<html>login</html>');
  await assert.rejects(forgeApi('/jobs'), /不是有效 JSON/);
  const aborted = new DOMException('Cancelled', 'AbortError');
  global.fetch = async () => { throw aborted; };
  await assert.rejects(forgeApi('/jobs'), e => e === aborted);
});
