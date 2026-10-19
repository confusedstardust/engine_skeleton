const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { loadFrontendTs } = require('./helpers/load_frontend_ts.cjs');
const workflow = loadFrontendTs(path.resolve(__dirname, '../forge_frontend_next/app/jobs/[jobId]/workspace-workflow.ts'));

test('scene retries use the continuous entry for draft failures and resume completion failures', () => {
  for (const phase of ['GAME_DESIGN', 'GAME_DESIGN_DRAFT']) {
    const retry = workflow.failedPhaseRetry({ status: 'FAILED', phase, options: { generation_mode: 'advanced' } });
    assert.equal(retry.path, 'phases/game_design');
    assert.equal(retry.stage, 'scenes');
  }
  const retry = workflow.failedPhaseRetry({ status: 'FAILED', phase: 'GAME_DESIGN_COMPLETION', options: {} });
  assert.equal(retry.path, 'phases/game_design_completion');
  assert.equal(retry.stage, 'scenes');
  assert.equal(workflow.failedPhaseRetry({ status: 'RUNNING', phase: 'GAME_DESIGN' }), null);
  assert.equal(workflow.failedPhaseRetry({ status: 'FAILED', phase: 'GAME_DESIGN', options: { generation_mode: 'auto' } }).path, 'run');
});

for (const dirty of [false, true]) {
  test(`outline confirmation starts a single continuous scene operation (dirty=${dirty})`, async () => {
    const calls = [];
    const events = [];
    const plan = { title: 'Test', characters: [], story_progression: [], endings: [] };
    const { useOutlineActions } = loadFrontendTs(path.resolve(__dirname, '../forge_frontend_next/app/jobs/[jobId]/use-outline-actions.ts'), {
      react: { useCallback: fn => fn, useEffect: () => {} },
      '../../../lib/api-client': { forgeApi: async (url, options) => {
        calls.push({ url, body: JSON.parse(options.body) });
        return { narrative_plan: plan };
      } },
    });
    const context = new Proxy({
      jobId: 'test-job', plan, planDirty: dirty, outlineLocked: false, planRef: { current: plan },
      refresh: async () => events.push('refresh'),
    }, { get: (target, key) => key in target ? target[key] : value => events.push([key, value]) });
    await useOutlineActions(context).nextToScenes();
    assert.deepEqual(calls.map(call => call.url), [
      ...(dirty ? ['/jobs/test-job/narrative-structure/sync'] : []),
      '/jobs/test-job/phases/game_design',
    ]);
    assert.deepEqual(calls.at(-1).body, { background: true });
    assert.ok(events.some(event => Array.isArray(event) && event[0] === 'setStage' && event[1] === 'scenes'));
    assert.ok(events.some(event => Array.isArray(event) && event[0] === 'setBusy' && event[1] === false));
  });
}
