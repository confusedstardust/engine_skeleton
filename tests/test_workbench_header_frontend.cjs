const { test } = require('node:test');
const assert = require('node:assert/strict');
const { loadFrontendTs } = require('./helpers/load_frontend_ts.cjs');

const { WorkspaceBack, WorkspaceHeader } = loadFrontendTs(
  'forge_frontend_next/node_modules/@narrativeos/ui/workspace-chrome.tsx',
);
const confirm = () => true;
const { WorkbenchHeader } = loadFrontendTs('forge_frontend_next/components/workbench-header.tsx', {
  './brand-logo': { default: () => null },
  './workspace-leave-guard': { useLeaveGuard: () => ({ confirm }) },
  '@narrativeos/ui/workspace-chrome': { WorkspaceHeader },
  '@narrativeos/ui/workspace-sidebar': { useBrowserOrigin: () => '' },
});
const fallback = '/teacher-ecosystem/';

test('Forge supplies the shared header with the plaza fallback, editor guard and page actions', () => {
  const header = WorkbenchHeader({ title: '工作台', children: '新建任务' });
  assert.equal(header.type, WorkspaceHeader);
  assert.equal(header.props.back.fallback, fallback);
  assert.equal(header.props.back.confirmNavigation, confirm);
  assert.equal(header.props.actions, '新建任务');
});

test('shared header omits the back action when the plaza has no back configuration', () => {
  const header = WorkspaceHeader({ title: '教师资源广场', logo: null });
  assert.equal(header.props.children[1], undefined);
});

test('shared back checks the leave guard, uses browser history, and falls back to the plaza', async () => {
  let allowed = false;
  const destinations = [];
  const button = WorkspaceBack({ fallback, siblingApp: 'http://localhost:3000/', confirmNavigation: () => allowed });
  const globals = {
    window: { navigation: { canGoBack: true } },
    document: { referrer: '' },
    history: { length: 1, back: () => destinations.push('previous') },
    location: { origin: 'http://localhost:3001', assign: href => destinations.push(href) },
  };
  const originals = Object.keys(globals).map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]);
  for (const [key, value] of Object.entries(globals)) Object.defineProperty(globalThis, key, { value, configurable: true });
  try {
    await button.props.onClick();
    assert.deepEqual(destinations, []);
    allowed = true;
    await button.props.onClick();
    globals.window.navigation.canGoBack = false;
    await button.props.onClick();
    globals.document.referrer = 'http://localhost:3000/';
    globals.history.length = 2;
    await button.props.onClick();
    assert.deepEqual(destinations, ['previous', fallback, 'previous']);
  } finally {
    for (const [key, descriptor] of originals) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else delete globalThis[key];
    }
  }
});

test('account menu policy stays identical regardless of page options', () => {
  const { AccountMenu } = loadFrontendTs('forge_frontend_next/components/account-menu.tsx', {
    'next/link': { default: () => null },
    '@narrativeos/ui': { AccountMenu: () => null },
    '../app/invite-identity': { accountClient: {}, accountSettingsUrl: () => 'https://portal.example/account', teacherResourcePlazaUrl: () => '/plaza' },
    '../app/base-path': { withBasePath: value => value },
  });
  const homepage = AccountMenu({});
  const workspace = AccountMenu({ className: 'nav-login', tour: 'invite', includeAdmin: false });
  assert.equal(homepage.props.includeAdmin, true);
  assert.equal(workspace.props.includeAdmin, true);
  assert.equal(homepage.props.client, workspace.props.client);
  assert.equal(homepage.props.plazaHref, workspace.props.plazaHref);
  assert.equal(homepage.props.settingsHref, 'https://portal.example/account');
  assert.equal(homepage.props.settingsHref, workspace.props.settingsHref);
});
