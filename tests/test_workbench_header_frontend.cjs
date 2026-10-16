const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('../forge_frontend_next/node_modules/typescript');
const { loadFrontendTs } = require('./helpers/load_frontend_ts.cjs');
const { WorkbenchHeader, WorkbenchNavigation } = loadFrontendTs(path.resolve(__dirname, '../forge_frontend_next/components/workbench-header.tsx'), {
  'next/link': { default: props => ({ type: 'a', props }) },
  './brand-logo': { default: () => ({ type: 'svg', props: {} }) },
  './account-menu': { AccountMenu: props => ({ type: 'account', props }) },
  './navigation-return': { ReturnLink: props => ({ type: 'return-link', props }) },
});
function render(node) {
  if (Array.isArray(node)) return node.map(render);
  if (!node || typeof node !== 'object' || !node.props) return node;
  if (typeof node.type === 'function') return render(node.type(node.props));
  return { type: node.type, props: { ...node.props, children: render(node.props.children) } };
}
function all(node, type) {
  if (Array.isArray(node)) return node.flatMap(child => all(child, type));
  if (!node || typeof node !== 'object' || !node.props) return [];
  return [...(node.type === type ? [node] : []), ...all(node.props.children, type)];
}

test('shared header retains Next route href, return fallback and one account menu', () => {
  const guard = () => {};
  const tree = render(WorkbenchHeader({ title: '工作台', brandHref: '/?workspace=1', fallback: '/history', label: '任务导航', onNavigate: guard, accountClassName: 'nav-login' }));
  assert.equal(all(tree, 'a')[0].props.href, '/?workspace=1');
  assert.equal(all(tree, 'a')[0].props.onClick, guard);
  assert.equal(all(tree, 'return-link')[0].props.fallback, '/history');
  assert.equal(all(tree, 'return-link')[0].props.onClick, guard);
  assert.equal(all(tree, 'nav')[0].props['aria-label'], '任务导航');
  assert.equal(all(tree, 'account').length, 1);
  assert.equal(all(tree, 'account')[0].props.includeAdmin, true);
});

test('invite navigation omits account and preserves custom actions', () => {
  const tree = render(WorkbenchHeader({ title: '邀请码', account: null, children: '新建任务' }));
  assert.equal(all(tree, 'account').length, 0);
  assert.ok(all(tree, 'nav')[0].props.children.includes('新建任务'));
});

test('generator brand and hamburger keep their original layout and mobile account props', () => {
  const tree = render(WorkbenchHeader({ title: '生成平台', brandHref: null, wrapBrand: false, afterNavigation: { type: 'button', props: { children: '菜单' } } }));
  assert.equal(all(tree, 'a').length, 0);
  assert.equal(all(tree, 'button').length, 1);
  assert.equal(all(tree, 'div').filter(node => node.props.className === 'workspace-nav-leading').length, 0);
  const mobile = render(WorkbenchNavigation({ className: 'mobile-menu', label: '移动端导航', accountClassName: 'mobile-login', accountTour: 'invite' }));
  assert.equal(mobile.props.className, 'mobile-menu');
  assert.equal(all(mobile, 'account')[0].props.className, 'mobile-login');
  assert.equal(all(mobile, 'account')[0].props.tour, 'invite');
});

test('admin trailing action remains after the account entry', () => {
  const tree = render(WorkbenchHeader({ title: '管理', children: '操作', afterAccount: '退出管理' }));
  const children = all(tree, 'nav')[0].props.children;
  assert.equal(children[1], '操作');
  assert.equal(children[2].type, 'account');
  assert.equal(children[3], '退出管理');
});

test('the task page still blocks navigation until unsaved changes are confirmed', async () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../forge_frontend_next/app/jobs/[jobId]/page.tsx'), 'utf8');
  const ast = ts.createSourceFile('page.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let initializer;
  function visit(node) {
    if (ts.isVariableDeclaration(node) && node.name.getText(ast) === 'handleNavigation') initializer = node.initializer.getText(ast);
    ts.forEachChild(node, visit);
  }
  visit(ast);
  assert.ok(initializer);
  let allowed = false, prevented = 0; const destinations = [];
  const context = { planDirty: true, scenesDirty: false, designDraftDirty: false, assetPromptDirty: false, confirm: async () => allowed, window: { location: { assign: value => destinations.push(value) } } };
  const js = ts.transpileModule(`const guard = ${initializer};`, { compilerOptions: { target: ts.ScriptTarget.ES2020 } }).outputText;
  const guard = vm.runInNewContext(`${js}\nguard`, context);
  const event = { preventDefault: () => prevented++, currentTarget: { href: 'http://localhost/history/' } };
  await guard(event); assert.deepEqual(destinations, []);
  allowed = true; await guard(event);
  assert.equal(prevented, 2); assert.deepEqual(destinations, ['http://localhost/history/']);
});
