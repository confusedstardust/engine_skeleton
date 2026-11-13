const test = require('node:test');
const assert = require('node:assert/strict');
const { loadFrontendTs } = require('./helpers/load_frontend_ts.cjs');
const { createRefreshPolling, refreshBatch } = loadFrontendTs('forge_frontend_next/lib/refresh-polling.ts');
const tick = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };
const result = (key = 'same', commit = () => {}, extra = {}) => ({ key, commit, ...extra });
function setup(task) {
  let state, id = 0;
  const timers = new Map();
  const polling = createRefreshPolling({ task, onState: value => { state = value; }, random: () => .5, now: () => 123,
    setTimer: (fn, ms) => { timers.set(++id, { fn, ms }); return id; }, clearTimer: id => timers.delete(id) });
  return { polling, timers, get state() { return state; } };
}

test('timer and manual requests share one inflight refresh and restart its clock', async () => {
  const pending = deferred(); let calls = 0;
  const h = setup(() => { calls++; return pending.promise; });
  h.polling.setActive(true);
  const a = h.polling.refresh(), b = h.polling.refresh();
  assert.equal(calls, 1);
  pending.resolve(result());
  assert.deepEqual(await Promise.all([a, b]), [true, true]);
  await tick();
  assert.equal(h.timers.size, 1);
  assert.equal(h.state.lastSyncedAt, 123);
  h.polling.dispose();
});

test('writes during an old refresh coalesce into one new snapshot and old data never commits', async () => {
  const batches = [deferred(), deferred()]; let calls = 0; const committed = [];
  const h = setup(() => batches[calls++].promise);
  const read = h.polling.refresh();
  const a = h.polling.refresh({ mutation: true }), b = h.polling.refresh({ mutation: true });
  batches[0].resolve(result('old', () => committed.push('old')));
  await tick();
  assert.equal(calls, 2);
  assert.deepEqual(committed, []);
  batches[1].resolve(result('new', () => committed.push('new')));
  assert.deepEqual(await Promise.all([read, a, b]), [true, true, true]);
  assert.deepEqual(committed, ['new']);
  h.polling.dispose();
});

test('quiet periods slow down, changes and running analysis accelerate, closed classes slow down', async () => {
  let next = result();
  const h = setup(async () => next);
  for (let i = 0; i < 4; i++) await h.polling.refresh();
  assert.equal(h.state.delayMs, 10000);
  for (let i = 0; i < 3; i++) await h.polling.refresh();
  assert.equal(h.state.delayMs, 20000);
  next = result('changed'); await h.polling.refresh();
  assert.equal(h.state.delayMs, 3000);
  next = result('changed', undefined, { closed: true }); await h.polling.refresh();
  assert.equal(h.state.delayMs, 60000);
  next = result('changed', undefined, { closed: true, active: true }); await h.polling.refresh();
  assert.equal(h.state.delayMs, 3000);
  h.polling.dispose();
});

test('visibility pause stops scheduling and dispose cancels pending data publication', async () => {
  let pending; let calls = 0, committed = 0;
  const h = setup(async () => { calls++; return pending ? pending.promise : result(); });
  h.polling.setActive(true); await tick();
  assert.equal(h.timers.size, 1);
  h.polling.setActive(false);
  assert.equal(h.timers.size, 0);
  pending = deferred();
  h.polling.setActive(true);
  assert.equal(calls, 2);
  const wait = h.polling.refresh();
  h.polling.dispose();
  pending.resolve(result('late', () => committed++));
  assert.equal(await wait, false); await tick();
  assert.equal(committed, 0);
  assert.equal(h.timers.size, 0);
});

test('closing a read-only view resumes the timer without an immediate full refresh', async () => {
  let calls = 0;
  const h = setup(async () => { calls++; return result(); });
  h.polling.setActive(true); await tick();
  h.polling.setActive(false);
  assert.equal(h.timers.size, 0);
  h.polling.setActive(true, { immediate: false });
  assert.equal(calls, 1);
  assert.equal(h.timers.size, 1);
  const scheduled = [...h.timers.values()][0];
  assert.equal(scheduled.ms, 5000);
  scheduled.fn(); await tick();
  assert.equal(calls, 2);
  h.polling.dispose();
});

test('closed collection can load once without scheduling further polling', async () => {
  const h = setup(async () => result('closed', undefined, { poll: false, closed: true }));
  h.polling.setActive(true); await tick();
  assert.equal(h.timers.size, 0);
  assert.equal(h.state.lastSyncedAt, 123);
  h.polling.dispose();
});

test('errors back off, authentication failures stop timers, manual retry can recover', async () => {
  let error = Error('unavailable');
  const h = setup(async () => { if (error) throw error; return result(); });
  for (const delay of [5000, 10000, 20000, 40000, 60000]) {
    assert.equal(await h.polling.refresh(), false);
    assert.equal(h.state.delayMs, delay);
  }
  error = Object.assign(Error('login required'), { status: 401 });
  h.polling.setActive(true); await tick();
  assert.equal(h.state.authRequired, true);
  assert.equal(h.timers.size, 0);
  error = null;
  assert.equal(await h.polling.refresh(), true);
  assert.equal(h.state.error, '');
  assert.equal(h.state.authRequired, false);
  h.polling.dispose();
});

test('one failing API waits for all other APIs before the full batch ends', async () => {
  const sibling = deferred(); let finished = false;
  const batch = refreshBatch([Promise.reject(Error('failure')), sibling.promise]).catch(() => { finished = true; });
  await tick(); assert.equal(finished, false);
  sibling.resolve('done'); await batch;
  assert.equal(finished, true);
});

test('hook pauses hidden views, resumes on visibility and aborts a replaced resource', async () => {
  const { hookHarness } = require('./helpers/hook_harness.cjs');
  const h = hookHarness();
  const originalDocument = global.document, originalWindow = global.window;
  const doc = Object.assign(new EventTarget(), { visibilityState: 'visible' });
  global.document = doc; global.window = new EventTarget();
  const { useRefreshPolling } = loadFrontendTs('forge_frontend_next/hooks/use-refresh-polling.ts', { react: h.react });
  let enabled = false, suspended = false, key = 'first', calls = 0, pending;
  const signals = [];
  const render = () => h.render(() => useRefreshPolling(async signal => {
    calls++; signals.push(signal); return pending ? pending.promise : result();
  }, { resetKey: key, enabled, suspended }));
  try {
    render(); assert.equal(calls, 0);
    enabled = true; render(); await tick(); assert.equal(calls, 1);
    suspended = true; render(); assert.equal(render().paused, true);
    suspended = false; render(); assert.equal(calls, 1, 'closing a read-only view resumes without immediate synchronization');
    doc.visibilityState = 'hidden'; doc.dispatchEvent(new Event('visibilitychange'));
    assert.equal(render().paused, true);
    pending = deferred();
    doc.visibilityState = 'visible'; doc.dispatchEvent(new Event('visibilitychange'));
    assert.equal(calls, 2);
    key = 'second'; render();
    assert.equal(signals[1].aborted, true);
    pending.resolve(result()); await tick();
  } finally {
    h.unmount(); global.document = originalDocument; global.window = originalWindow;
  }
});
