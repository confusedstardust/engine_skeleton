const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('../forge_frontend_next/node_modules/typescript');

const page = ts.createSourceFile('page.tsx', fs.readFileSync(`${__dirname}/../forge_frontend_next/app/jobs/[jobId]/page.tsx`, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const workbench = ts.createSourceFile('workbench.tsx', fs.readFileSync(`${__dirname}/../forge_frontend_next/components/laper-asset-workbench.tsx`, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
function find(root, predicate) {
  if (predicate(root)) return root;
  return ts.forEachChild(root, child => find(child, predicate));
}
function load(context) {
  const names = ['saveStagedPresentation', 'retryPhase', 'retryFailedPhase'];
  const functions = names.map(name => find(page, node => ts.isFunctionDeclaration(node) && node.name?.text === name).getText(page));
  const handler = find(workbench, node => ts.isJsxAttribute(node) && node.name.text === 'onClick' && node.initializer?.getText(workbench).includes('props.retryAction?.(')).initializer.expression.getText(workbench);
  const js = ts.transpileModule(`${functions.join('\n')}\nconst clickRetry = ${handler};`, { compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS } }).outputText;
  return vm.runInNewContext(`${js}\n({ retryPhase, retryFailedPhase, clickRetry })`, context);
}
function setup(failAt = '') {
  const calls = [], errors = [], busy = [];
  const context = {
    jobId: 'job-1', data: { job: { draft_revision: 4 } },
    failedRetry: { stage: 'assets', path: 'phases/game_build', pendingMessage: '', successMessage: '' },
    setBusy: value => busy.push(value), setStage() {}, setMessage() {},
    setErrorMessage: error => errors.push(error), refresh: async () => {},
    setData: update => { context.data = update(context.data); },
    api: async (url, options) => {
      calls.push({ url, body: JSON.parse(options.body) });
      if (url.endsWith(failAt) && failAt) throw new Error('save failed');
      return { job: { draft_revision: 4 + calls.length } };
    },
    hasStagedPresentation: true,
    musicDrafts: { 'start.txt': 'music.mp3' }, effectDrafts: {},
    avatarCropDrafts: { 'figure_cen_xun.webp': { zoom: 1.2, offsetX: 0.1, offsetY: 0 } },
    setAvatarCropDrafts: value => { context.avatarCropDrafts = value; }
  };
  const loaded = load(context);
  let pending;
  context.props = { retryAction: staged => (pending = loaded.retryPhase(staged)) };
  return { context, loaded, calls, errors, busy, click: async () => { loaded.clickRetry(); await pending; await Promise.resolve(); } };
}

test('retry button saves avatar then presentation with successive revisions before building', async () => {
  const run = setup();
  await run.click();
  assert.deepEqual(run.calls.map(call => call.url), ['/jobs/job-1/assets/avatar-crop', '/jobs/job-1/scene-presentation-draft', '/jobs/job-1/phases/game_build']);
  assert.equal(run.calls[0].body.base_revision, 4);
  assert.equal(run.calls[1].body.base_revision, 5);
  assert.equal(run.context.data.job.draft_revision, 6);
  assert.equal(Object.keys(run.context.avatarCropDrafts).length, 0);
  assert.deepEqual(run.busy, [true, false]);
});

test('save failure keeps crop edits and prevents generation', async () => {
  const run = setup('avatar-crop');
  await run.click();
  assert.equal(run.calls.length, 1);
  assert.ok(run.context.avatarCropDrafts['figure_cen_xun.webp']);
  assert.equal(run.errors.length, 1);
  assert.deepEqual(run.busy, [true, false]);
});

test('partial save retains latest revision and edits for another retry', async () => {
  const run = setup('scene-presentation-draft');
  await run.click();
  assert.equal(run.calls.length, 2);
  assert.equal(run.context.data.job.draft_revision, 5);
  assert.ok(run.context.avatarCropDrafts['figure_cen_xun.webp']);
});

test('retry without edits preserves the failed phase endpoint', async () => {
  const run = setup();
  run.context.hasStagedPresentation = false;
  run.context.failedRetry.path = 'phases/asset_review';
  await run.click();
  assert.equal(run.calls.length, 1);
  assert.equal(run.calls[0].url, '/jobs/job-1/phases/asset_review');
});

test('outline and scene retry ignore click events and retry their own phase', async () => {
  const run = setup();
  run.context.failedRetry.path = 'phases/narrative';
  assert.equal(await run.loaded.retryFailedPhase({ type: 'click' }), true);
  assert.equal(run.calls.length, 1);
  assert.equal(run.calls[0].url, '/jobs/job-1/phases/narrative');
});
