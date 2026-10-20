const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { loadFrontendTs } = require('./helpers/load_frontend_ts.cjs');
const { hookHarness } = require('./helpers/hook_harness.cjs');
const pending = (extra = {}) => ({ id: 'order1', name: '私人支付测试', status: 'PENDING', fulfillment_status: 'PENDING', credits: 1, ...extra });
function setup(t, overrides = {}, callbacks = {}) {
  const harness = hookHarness(); let poll; const notifications = [];
  const previous = global.window; global.window = { dispatchEvent: event => notifications.push(event.type) };
  t.after(() => { harness.unmount(); if (previous === undefined) delete global.window; else global.window = previous; });
  const adapter = {
    list: async () => [], create: async () => pending(), read: async () => pending(), close: async () => pending({ status: 'CLOSED' }),
    balance: async () => ({ available: 101 }), accepts: order => order.name === '私人支付测试', conflictMessage: '正式订单未处理', ...overrides,
  };
  let key = 0;
  const { usePaymentOrder } = loadFrontendTs(path.resolve(__dirname, '../forge_frontend_next/hooks/use-payment-order.ts'), {
    react: harness.react,
    './use-polling': { usePolling: (task, options) => { poll = { task, options }; } },
    '../app/random-uuid': { randomUUID: () => `key-${++key}` },
    '../components/credit-balance': { creditBalanceChangedEvent: 'credit-change' },
  });
  const render = () => harness.render(() => usePaymentOrder(adapter, callbacks));
  render(); return { render, adapter, notifications, poll: () => poll, unmount: () => harness.unmount() };
}

test('ambiguous creation retries with the same key and rejects rapid double submissions', async t => {
  const payloads = []; let fail = true;
  const h = setup(t, { create: async body => { payloads.push(body); if (fail) throw Error('lost response'); return pending(); }, list: async () => { throw Error('offline'); } });
  let value = h.render(); await value.start({ product_id: 'p1' });
  value = h.render(); assert.match(value.error, /lost response/);
  fail = false; const one = value.start({ product_id: 'p1' }), two = value.start({ product_id: 'p1' }); await Promise.all([one, two]);
  value = h.render(); assert.equal(payloads.length, 2); assert.equal(payloads[0].request_key, payloads[1].request_key); assert.equal(value.open, true);
});

test('creation response loss recovers a durable pending order from history', async t => {
  const h = setup(t, { create: async () => { throw Error('lost'); }, list: async () => [pending()] });
  await h.render().start(); const value = h.render(); assert.equal(value.order.id, 'order1'); assert.equal(value.open, true);
});

test('a pending formal order blocks test creation, reads and cancellation', async t => {
  let writes = 0; const h = setup(t, { create: async () => { writes++; return pending(); }, close: async () => { writes++; } });
  h.render().restore([pending({ name: 'Creator' })]); let value = h.render();
  assert.equal(h.poll().options.enabled, false); assert.equal(value.open, false);
  await value.start(); value = h.render(); assert.equal(value.error, '正式订单未处理'); await value.refresh(true); assert.equal(writes, 0);
});

test('late pending reads cannot overwrite a manually closed order', async t => {
  let finish; const h = setup(t, { read: () => new Promise(resolve => { finish = resolve; }) });
  h.render().restore([pending()]); let value = h.render(); const read = h.poll().task(new AbortController().signal);
  await value.refresh(true); finish(pending()); await read;
  value = h.render(); assert.equal(value.order.status, 'CLOSED'); assert.equal(h.poll().options.enabled, false);
});

test('payment confirmation alone keeps polling; fulfillment refreshes balance and notifies once', async t => {
  let fulfilled = false, proofs = 0;
  const h = setup(t, { read: async () => pending({ status: 'PAID', fulfillment_status: fulfilled ? 'FULFILLED' : 'PENDING' }) }, { onRead: async () => { proofs++; } });
  h.render().restore([pending()]); h.render();
  assert.equal(await h.poll().task(new AbortController().signal), true); h.render(); assert.equal(h.poll().options.enabled, true); assert.equal(h.notifications.length, 0);
  fulfilled = true; assert.equal(await h.poll().task(new AbortController().signal), false);
  let value = h.render(); assert.equal(value.balance.available, 101); assert.equal(h.poll().options.enabled, false);
  await value.refresh(); value = h.render(); assert.equal(proofs, 3); assert.equal(h.notifications.length, 1); assert.equal(value.creditedBalance.available, 101);
});

test('proof lookup failure retains the confirmed order and lets the user recheck evidence', async t => {
  const h = setup(t, { read: async () => pending({ status: 'PAID', fulfillment_status: 'FULFILLED' }) }, { onRead: async () => { throw Error('proof unavailable'); } });
  h.render().restore([pending()]); const value = h.render(); await value.refresh();
  const next = h.render(); assert.equal(next.order.status, 'PAID'); assert.equal(next.balance.available, 101); assert.match(next.error, /proof unavailable/);
});

test('unmount discards late creation results and does not open checkout', async t => {
  let finish; const h = setup(t, { create: () => new Promise(resolve => { finish = resolve; }) });
  const request = h.render().start(); h.unmount(); finish(pending()); await request;
  assert.equal(h.render().order, null); assert.equal(h.render().open, false);
});

test('an already-paid idempotent creation response still loads test evidence and balance', async t => {
  let proofs = 0;
  const h = setup(t, { create: async () => pending({ status: 'PAID', fulfillment_status: 'FULFILLED' }) }, { onRead: async () => { proofs++; } });
  await h.render().start(); const value = h.render();
  assert.equal(proofs, 1); assert.equal(value.balance.available, 101); assert.equal(value.open, true);
  assert.equal(h.poll().options.enabled, false);
});

test('a paid order awaiting fulfillment is resumed instead of creating a second payment', async t => {
  let creates = 0;
  const h = setup(t, { create: async () => { creates++; return pending(); } });
  h.render().restore([pending({ status: 'PAID', fulfillment_status: 'PENDING' })]);
  const value = h.render(); await value.start();
  assert.equal(creates, 0); assert.equal(h.poll().options.enabled, true);
});
