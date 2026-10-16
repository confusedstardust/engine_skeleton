const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { loadFrontendTs } = require('./helpers/load_frontend_ts.cjs');
const { startPolling } = loadFrontendTs(path.resolve(__dirname, '../forge_frontend_next/lib/polling.ts'));
const flush = async () => { for (let i = 0; i < 15; i++) await Promise.resolve(); };
function timers(t) {
  const oldSet = global.setTimeout, oldClear = global.clearTimeout;
  let now = 0, id = 0; const pending = new Map();
  global.setTimeout = (callback, delay) => { pending.set(++id, { callback, at: now + delay }); return id; };
  global.clearTimeout = key => pending.delete(key);
  t.after(() => { global.setTimeout = oldSet; global.clearTimeout = oldClear; });
  return { pending, async tick(ms) {
    now += ms;
    for (const [key, timer] of [...pending]) if (timer.at <= now) { pending.delete(key); timer.callback(); }
    await flush();
  } };
}

test('slow requests never overlap and terminal results stop all future polling', async t => {
  const clock = timers(t); let calls = 0, finish;
  const stop = startPolling(async () => { calls++; return new Promise(resolve => { finish = resolve; }); }, { intervalMs: 10 });
  await clock.tick(1000); assert.equal(calls, 1); assert.equal(clock.pending.size, 0);
  finish(false); await flush(); await clock.tick(1000);
  assert.equal(calls, 1); assert.equal(clock.pending.size, 0); stop();
});

test('failures back off, cap the retry delay, and successful reads restore the normal interval', async t => {
  const clock = timers(t); let calls = 0; const errors = [];
  const stop = startPolling(async () => { calls++; if (calls <= 2) throw Error('network'); return calls < 4; }, { intervalMs: 10, maxIntervalMs: 30, onError: e => errors.push(e) });
  await flush(); await clock.tick(19); assert.equal(calls, 1);
  await clock.tick(1); assert.equal(calls, 2);
  await clock.tick(29); assert.equal(calls, 2);
  await clock.tick(1); assert.equal(calls, 3);
  await clock.tick(10); assert.equal(calls, 4); assert.equal(errors.length, 2);
  assert.equal(clock.pending.size, 0); stop();
});

test('unmount cancels in-flight work and prevents rescheduling or error reporting', async t => {
  const clock = timers(t); let signal, reject; const errors = [];
  const stop = startPolling(async value => { signal = value; return new Promise((_, fail) => { reject = fail; }); }, { intervalMs: 10, onError: e => errors.push(e) });
  stop(); assert.equal(signal.aborted, true); reject(Error('aborted')); await flush(); await clock.tick(1000);
  assert.equal(clock.pending.size, 0); assert.deepEqual(errors, []);
});

test('changing poll targets waits for the previous in-flight operation to settle', async t => {
  timers(t); const slot = { current: null }; let finish, next = 0;
  const stopOld = startPolling(() => new Promise(resolve => { finish = resolve; }), { intervalMs: 10, slot });
  stopOld(); const stopNew = startPolling(async () => { next++; return false; }, { intervalMs: 10, slot });
  await flush(); assert.equal(next, 0);
  finish(true); await flush(); assert.equal(next, 1); stopNew();
});
