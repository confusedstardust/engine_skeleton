const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { loadFrontendTs } = require('./helpers/load_frontend_ts.cjs');
const file = path.resolve(__dirname, '../forge_frontend_next/app/jobs/[jobId]/use-outline-actions.ts');

function setup() {
  const original = { title: 'Original', characters: [], story_progression: [], endings: [] };
  const state = { plan: original, dirty: false, data: { nodes: [{ key: 'narrative_plan', content: JSON.stringify(original) }] } };
  const effects = [];
  const notifications = [];
  let resolve;
  const { useOutlineActions } = loadFrontendTs(file, {
    react: { useCallback: fn => fn, useEffect: fn => effects.push(fn) },
    '../../../lib/api-client': { forgeApi: () => new Promise(done => { resolve = done; }) },
  });
  const context = new Proxy({
    notify: (...args) => notifications.push(args),
    jobId: 'test', plan: original, planDirty: true, outlineLocked: false, planRef: { current: original },
    setData: fn => { state.data = fn(state.data); },
    setPlan: plan => { state.plan = plan; }, setPlanDirty: dirty => { state.dirty = dirty; },
    refresh: async () => {},
  }, { get: (target, key) => key in target ? target[key] : () => {} });
  return { state, context, effects, notifications, actions: useOutlineActions(context), respond: value => resolve(value) };
}

test('blank blocks update the page cache and survive successful autosave', async () => {
  const h = setup();
  const next = { ...h.state.plan, characters: [{ id: 'character_0', name: '' }] };
  h.actions.updatePlan(next);
  assert.deepEqual(JSON.parse(h.state.data.nodes[0].content), next);
  assert.equal(h.state.dirty, true);
  const saving = h.actions.syncNarrativeStructure(next, { quiet: true });
  h.respond({ narrative_plan: next, issues: [] });
  await saving;
  assert.equal(h.state.plan.characters.length, 1);
  assert.equal(JSON.parse(h.state.data.nodes[0].content).characters.length, 1);
  assert.equal(h.state.dirty, false);
  assert.equal(h.notifications.length, 0, "autosave stays quiet");
});

for (const quiet of [true, false]) {
  test(`a save response cannot overwrite subsequent edits (quiet=${quiet})`, async () => {
    const h = setup();
    const saving = h.actions.syncNarrativeStructure(h.state.plan, { quiet });
    const edited = { ...h.state.plan, title: 'New typing' };
    h.actions.updatePlan(edited);
    h.respond({ narrative_plan: h.context.plan, issues: [] });
    await saving;
    assert.equal(h.state.plan.title, 'New typing');
    assert.equal(JSON.parse(h.state.data.nodes[0].content).title, 'New typing');
    assert.equal(h.state.dirty, true);
  });
}

test('autosave waits eight seconds and cancels its timer when editing resumes', () => {
  const h = setup();
  const oldWindow = global.window;
  const calls = [];
  global.window = { setTimeout: (fn, delay) => { calls.push(delay); return 42; }, clearTimeout: id => calls.push(id) };
  try {
    const cleanup = h.effects[0]();
    assert.deepEqual(calls, [8000]);
    cleanup();
    assert.deepEqual(calls, [8000, 42]);
  } finally { global.window = oldWindow; }
});


test('manual outline save reports success through the shared notification callback', async () => {
  const h = setup();
  const saving = h.actions.savePlan();
  h.respond({ narrative_plan: h.context.plan, issues: [] });
  await saving;
  assert.deepEqual(h.notifications, [['大纲和流程图已保存。', 'success']]);
});
