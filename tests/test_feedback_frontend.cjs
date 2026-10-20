const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { loadFrontendTs } = require('./helpers/load_frontend_ts.cjs');
const { hookHarness } = require('./helpers/hook_harness.cjs');

test('operation error feedback waits for checkout close, deduplicates rerenders, and allows a new failed attempt', () => {
  const harness = hookHarness();
  const events = [];
  const { useErrorToast } = loadFrontendTs(path.resolve(__dirname, '../forge_frontend_next/components/ui/toast.tsx'), {
    react: { ...harness.react, createContext: () => ({}), useContext: () => (...args) => events.push(args) },
  });
  let message = 'Order failed';
  let suppressed = true;
  const render = () => harness.render(() => useErrorToast(message, suppressed));
  render(); assert.deepEqual(events, []);
  suppressed = false; render(); assert.deepEqual(events, [['Order failed', 'error']]);
  render(); assert.equal(events.length, 1);
  message = ''; render();
  message = 'Order failed'; render(); assert.equal(events.length, 2);
  harness.unmount();
});

test('payment polling errors stay inline and never become toasts when checkout closes', async () => {
  const harness = hookHarness();
  const events = [];
  let poll;
  let failRead = true;
  const react = { ...harness.react, createContext: () => ({}), useContext: () => (...args) => events.push(args) };
  const { usePaymentOrder } = loadFrontendTs(path.resolve(__dirname, '../forge_frontend_next/hooks/use-payment-order.ts'), {
    react,
    './use-polling': { usePolling: (task, options) => { poll = { task, options }; } },
  });
  const { useErrorToast } = loadFrontendTs(path.resolve(__dirname, '../forge_frontend_next/components/ui/toast.tsx'), { react });
  const order = { id: 'pending', status: 'PENDING', fulfillment_status: 'PENDING' };
  const adapter = { accepts: () => true, read: async () => { if (failRead) throw Error('poll failed'); return order; } };
  const render = () => harness.render(() => {
    const checkout = usePaymentOrder(adapter);
    useErrorToast(checkout.operationError, checkout.open);
    return checkout;
  });
  const pollOnce = async () => { try { await poll.task(new AbortController().signal); } catch (error) { poll.options.onError(error); } };
  try {
    let checkout = render();
    checkout.restore([order]); checkout = render();
    await pollOnce(); checkout = render();
    assert.equal(checkout.error, 'poll failed', 'failure remains available inside checkout');
    checkout.setOpen(false); checkout = render();
    assert.equal(poll.options.enabled, true);
    await pollOnce(); checkout = render();
    assert.deepEqual(events, [], 'closing the dialog and subsequent failed polls stay quiet');
    failRead = false; await pollOnce(); checkout = render();
    assert.equal(checkout.error, '');
    failRead = true; await checkout.refresh(); checkout = render();
    assert.deepEqual(events, [['poll failed', 'error']], 'explicit refresh failure still notifies');
    checkout = render(); assert.equal(events.length, 1);
  } finally { harness.unmount(); }
});
