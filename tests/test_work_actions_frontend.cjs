const test = require('node:test');
const assert = require('node:assert/strict');
const { loadFrontendTs } = require('./helpers/load_frontend_ts.cjs');
const { hookHarness } = require('./helpers/hook_harness.cjs');
const job = { id: 'work', status: 'DONE', has_published_build: true };
const deferred = () => { let resolve; const promise = new Promise(r => resolve = r); return { promise, resolve }; };
function setup(api, confirm = async () => true) {
  const harness = hookHarness();
  const notices = [];
  const options = { confirm, notify: (...args) => notices.push(args) };
  const { useWorkActions } = loadFrontendTs('forge_frontend_next/hooks/use-work-actions.ts', {
    react: harness.react, '../lib/api-client': { forgeApi: api },
  });
  const render = () => harness.render(() => useWorkActions(options));
  return { render, harness, notices };
}

test('publication confirmation reserves the operation before awaiting and blocks other mutations', async () => {
  const confirmation = deferred(); let calls = 0;
  const state = setup(async () => { calls++; return { published: false }; }, () => confirmation.promise);
  const actions = state.render();
  const first = actions.changePublication(job, true);
  assert.equal(await actions.changePublication(job, true), null);
  assert.equal(await actions.rename(job, 'new'), null);
  assert.equal(calls, 0);
  confirmation.resolve(true);
  await first;
  assert.equal(calls, 1);
  assert.equal(state.render().busy, null);
  assert.deepEqual(state.notices, [['已取消生态发布。', 'success']]);
});

test('a stale publication read cannot overwrite a successful publish', async () => {
  const read = deferred();
  const state = setup(async (path, init) => init ? { published: true } : read.promise);
  const actions = state.render();
  const pending = actions.loadPublication(job);
  await actions.changePublication(job);
  read.resolve({ published: false }); await pending;
  assert.equal(state.render().publications.work.published, true);
});

test('renaming does not discard an in-flight initial publication read', async () => {
  const read = deferred();
  const state = setup(async (path, init) => init ? { job: { ...job, title: 'new' } } : read.promise);
  const actions = state.render();
  const pending = actions.loadPublication(job);
  await actions.rename(job, 'new');
  read.resolve({ published: true }); await pending;
  assert.equal(state.render().publications.work.published, true);
});

test('publication reads are deduplicated and skipped during mutation', async () => {
  const response = deferred(); let calls = 0;
  const state = setup(async () => { calls++; return response.promise; });
  const actions = state.render();
  const first = actions.loadPublication(job);
  await actions.loadPublication(job);
  assert.equal(calls, 1);
  response.resolve({ published: false }); await first;
  const mutation = actions.changePublication(job);
  await actions.loadPublication(job);
  await mutation;
  assert.equal(calls, 2);
});

test('rename validates, trims and preserves errors until a successful retry', async () => {
  let calls = 0, fail = true;
  const state = setup(async (path, init) => {
    calls++; if (fail) throw Error('保存失败');
    return { job: { ...job, title: JSON.parse(init.body).title } };
  });
  let actions = state.render();
  await actions.rename(job, ' '); await actions.rename(job, 'a'.repeat(161));
  assert.equal(calls, 0);
  await actions.rename(job, ' new ');
  assert.equal(state.render().errors['work:title'], '保存失败');
  fail = false; actions = state.render();
  assert.equal((await actions.rename(job, ' new ')).title, 'new');
  assert.equal(state.render().errors['work:title'], '');
});

test('publication failure releases the lock and allows retry with consistent feedback', async () => {
  let fail = true;
  const state = setup(async () => { if (fail) throw Error('发布失败'); return { published: true }; });
  const actions = state.render();
  await actions.changePublication(job);
  assert.equal(state.render().busy, null);
  assert.equal(state.render().errors['work:publication'], '发布失败');
  fail = false; await actions.changePublication(job);
  assert.equal(state.render().errors['work:publication'], '');
  assert.deepEqual(state.notices, [['发布失败', 'error'], ['已发布到教师资源广场。', 'success']]);
});

test('building work blocks all mutations; cancellation does not call the backend', async () => {
  let calls = 0;
  const state = setup(async () => { calls++; }, async () => false);
  const actions = state.render();
  for (const blocked of [{ ...job, build_state: 'BUILDING' }, { ...job, status: 'RUNNING' }, { ...job, status: 'QUEUED' }]) {
    await actions.rename(blocked, 'new'); await actions.changePublication(blocked); await actions.remove(blocked);
  }
  await actions.changePublication(job, true);
  assert.equal(calls, 0);
  assert.equal(state.render().busy, null);
});

test('leaving the page during confirmation suppresses the request and late success callbacks', async () => {
  const confirmation = deferred(); let calls = 0;
  const state = setup(async () => { calls++; }, () => confirmation.promise);
  const pending = state.render().changePublication(job, true);
  state.harness.unmount(); confirmation.resolve(true);
  assert.equal(await pending, null);
  assert.equal(calls, 0);
  assert.deepEqual(state.notices, []);
});
