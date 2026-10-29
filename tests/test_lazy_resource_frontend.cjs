const test = require('node:test');
const assert = require('node:assert/strict');
const { hookHarness } = require('./helpers/hook_harness.cjs');
const { loadFrontendTs } = require('./helpers/load_frontend_ts.cjs');
const tick = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };

test('lazy resources do not fetch while hidden, deduplicate demand and reuse cached data', async () => {
  const h = hookHarness();
  const { useLazyResource } = loadFrontendTs('forge_frontend_next/hooks/use-lazy-resource.ts', { react: h.react });
  let enabled = false, calls = 0;
  const gate = deferred();
  const render = () => h.render(() => useLazyResource('classes', async () => { calls++; return gate.promise; }, enabled));
  try {
    render(); assert.equal(calls, 0);
    enabled = true; render();
    const resource = render();
    const a = resource.load(), b = resource.load();
    assert.equal(calls, 1);
    gate.resolve(['班级']); await Promise.all([a, b]);
    assert.deepEqual(render().data, ['班级']);
    enabled = false; render(); enabled = true; render();
    assert.equal(calls, 1);
  } finally { h.unmount(); }
});

test('submission changes mark hidden statistics dirty and fetch once when analysis is opened', async () => {
  const h = hookHarness();
  const { useLazyResource } = loadFrontendTs('forge_frontend_next/hooks/use-lazy-resource.ts', { react: h.react });
  let enabled = true, calls = 0;
  const render = () => h.render(() => useLazyResource('stats', async () => ++calls, enabled));
  try {
    render(); await tick(); assert.equal(render().data, 1);
    enabled = false; render(); render().invalidate(); render();
    assert.equal(calls, 1);
    enabled = true; render(); await tick();
    assert.equal(render().data, 2);
    assert.equal(render().dirty, false);
    assert.equal(calls, 2);
  } finally { h.unmount(); }
});

test('late responses cannot overwrite another resource and failures require explicit retry', async () => {
  const h = hookHarness();
  const { useLazyResource } = loadFrontendTs('forge_frontend_next/hooks/use-lazy-resource.ts', { react: h.react });
  const old = deferred(); let key = 'old', fail = false, calls = 0;
  const render = () => h.render(() => {
    const captured = key;
    return useLazyResource(key, async () => { calls++; if (captured === 'old') return old.promise; if (fail) throw Error('failure'); return captured; }, true);
  });
  try {
    render(); key = 'new'; render(); await tick();
    old.resolve('late'); await tick();
    assert.equal(render().data, 'new');
    fail = true; await render().load(true); render(); await tick();
    assert.equal(render().error, 'failure');
    const before = calls; render(); render(); assert.equal(calls, before);
    fail = false; await render().load(true);
    assert.equal(render().error, '');
    assert.equal(render().data, 'new');
  } finally { h.unmount(); }
});

test('submission fingerprint ignores ordering but detects same-count replacements and renames', () => {
  const { submissionKey } = loadFrontendTs('forge_frontend_next/domain/submission-changes.ts');
  const rows = [{ id: 'a', display_name: '学生甲', submitted_at: 'time' }, { id: 'b', display_name: '学生乙', submitted_at: 'time' }];
  assert.equal(submissionKey(rows), submissionKey([...rows].reverse()));
  assert.notEqual(submissionKey(rows), submissionKey([{ ...rows[0], display_name: '更正姓名' }, rows[1]]));
  assert.notEqual(submissionKey(rows), submissionKey([{ ...rows[0], id: 'replacement' }, rows[1]]));
});
