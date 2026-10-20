const test = require('node:test');
const assert = require('node:assert/strict');
const { loadFrontendTs } = require('./helpers/load_frontend_ts.cjs');
const { hookHarness } = require('./helpers/hook_harness.cjs');
const tick = () => new Promise((resolve) => setImmediate(resolve));
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((a, b) => {
    resolve = a;
    reject = b;
  });
  return { promise, resolve, reject };
};

test('list serializes loads, deduplicates within batches, and retries the failed cursor', async () => {
  const h = hookHarness();
  const { useIncrementalList } = loadFrontendTs('forge_frontend_next/hooks/use-incremental-list.ts', {
    react: h.react,
  });
  const first = deferred(),
    calls = [];
  let failed = false;
  const options = {
    resetKey: 'a',
    initialCursor: 0,
    keyOf: (item) => item.id,
    load: async (cursor) => {
      calls.push(cursor);
      if (!cursor) return first.promise;
      if (!failed) {
        failed = true;
        throw new Error('retry me');
      }
      return { items: [{ id: 'a' }, { id: 'b' }], next: 2, hasMore: false };
    },
  };
  const render = () => h.render(() => useIncrementalList(options));
  let list = render();
  await list.loadNext();
  assert.deepEqual(calls, [0]);
  first.resolve({ items: [{ id: 'a' }, { id: 'a' }], next: 1, hasMore: true, total: 2 });
  await tick();
  list = render();
  assert.equal(list.items.length, 1);
  await list.loadNext();
  list = render();
  assert.equal(list.error, 'retry me');
  await list.loadNext();
  list = render();
  assert.deepEqual(calls, [0, 1, 1]);
  assert.deepEqual(
    list.items.map((x) => x.id),
    ['a', 'b'],
  );
  assert.equal(list.hasMore, false);
  await list.loadNext();
  assert.equal(calls.length, 3);
  h.unmount();
});

test('filter changes and unmount abort requests and discard stale results', async () => {
  const h = hookHarness();
  const { useIncrementalList } = loadFrontendTs('forge_frontend_next/hooks/use-incremental-list.ts', {
    react: h.react,
  });
  const old = deferred(),
    fresh = deferred();
  let signal;
  let options = {
    resetKey: 'old',
    initialCursor: 1,
    keyOf: (item) => item.id,
    load: (_, s) => {
      signal = s;
      return old.promise;
    },
  };
  const render = () => h.render(() => useIncrementalList(options));
  render();
  options = { ...options, resetKey: 'new', load: () => fresh.promise };
  render();
  assert.equal(signal.aborted, true);
  old.resolve({ items: [{ id: 'old' }], next: 2, hasMore: false });
  await tick();
  assert.deepEqual(render().items, []);
  fresh.resolve({ items: [{ id: 'new' }], next: 2, hasMore: false });
  await tick();
  assert.deepEqual(render().items, [{ id: 'new' }]);
  h.unmount();
});

class FakeAudio extends EventTarget {
  constructor(src) {
    super();
    this.src = src;
    this.paused = true;
    this.currentTime = 0;
  }
  async play() {
    this.paused = false;
    this.dispatchEvent(new Event('play'));
  }
  pause() {
    this.paused = true;
    this.dispatchEvent(new Event('pause'));
  }
}
test('voice, library and blob previews share ownership; stale blobs never play and URLs are released', async () => {
  const original = { Audio: global.Audio, create: URL.createObjectURL, revoke: URL.revokeObjectURL };
  const created = [],
    revoked = [];
  global.Audio = FakeAudio;
  URL.createObjectURL = () => {
    const url = 'blob:' + created.length;
    created.push(url);
    return url;
  };
  URL.revokeObjectURL = (url) => revoked.push(url);
  try {
    const cache = new Map(),
      owner = loadFrontendTs('forge_frontend_next/lib/audio-preview.ts', {}, cache);
    function mount(source) {
      const h = hookHarness();
      const { useAudioPreview } = loadFrontendTs('forge_frontend_next/hooks/use-audio-preview.ts', {
        react: h.react,
        '../lib/audio-preview': owner,
      });
      const render = () => h.render(() => useAudioPreview(source));
      render();
      let value = render();
      value.audioRef.current = new FakeAudio(source);
      return { h, render };
    }
    const a = mount('voice'),
      b = mount('library');
    await a.render().play('voice');
    assert.equal(a.render().playing, true);
    await b.render().play('library');
    assert.equal(a.render().audioRef.current.paused, true);
    assert.equal(a.render().playing, false);
    const pending = deferred();
    const request = a.render().play('old', () => pending.promise);
    await b.render().play('library');
    pending.resolve(new Blob(['old']));
    await request;
    assert.equal(created.length, 0);
    await a.render().play('music', async () => new Blob(['music']));
    assert.equal(a.render().activeKey, 'music');
    a.h.unmount();
    assert.deepEqual(revoked, created);
    b.h.unmount();
  } finally {
    global.Audio = original.Audio;
    URL.createObjectURL = original.create;
    URL.revokeObjectURL = original.revoke;
  }
});

test('play failures release ownership and expose retryable errors', async () => {
  const h = hookHarness();
  const { useAudioPreview } = loadFrontendTs('forge_frontend_next/hooks/use-audio-preview.ts', { react: h.react });
  const render = () => h.render(() => useAudioPreview('broken'));
  render();
  render().audioRef.current = Object.assign(new FakeAudio('broken'), {
    play: async () => {
      throw new Error('blocked');
    },
  });
  await render().play('broken');
  assert.equal(render().playing, false);
  assert.equal(render().activeKey, null);
  assert.equal(render().error, 'blocked');
  h.unmount();
});
