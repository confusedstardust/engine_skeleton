const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { snapshot, verify, assertVersion } = require('../forge_frontend_next/node_modules/@narrativeos/ui/verify-release.cjs');

function fixture(run) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'shared-ui-release-'));
  try {
    fs.writeFileSync(path.join(root, 'package.json'), JSON.stringify({ version: '1.0.0' }));
    fs.writeFileSync(path.join(root, 'account-menu.tsx'), 'export const account = true;\n');
    fs.writeFileSync(path.join(root, 'release-manifest.json'), JSON.stringify(snapshot(root)));
    run(root);
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
}
test('the installed shared UI release has a complete matching manifest', () => {
  verify(path.resolve(__dirname, '../forge_frontend_next/node_modules/@narrativeos/ui'));
});
test('editing, adding or removing runtime files invalidates the release', () => {
  for (const change of [
    root => fs.appendFileSync(path.join(root, 'account-menu.tsx'), 'changed'),
    root => fs.writeFileSync(path.join(root, 'new-component.tsx'), 'new'),
    root => fs.unlinkSync(path.join(root, 'account-menu.tsx')),
  ]) fixture(root => { change(root); assert.throws(() => verify(root), /manifest mismatch/); });
});
test('Windows and Linux line endings produce the same release identity', () => fixture(root => {
  fs.writeFileSync(path.join(root, 'account-menu.tsx'), 'export const account = true;\r\n');
  verify(root);
}));
test('changed content requires a strictly greater release version', () => {
  const previous = { version: '1.2.3', files: { code: 'old' } };
  assertVersion(previous, previous);
  for (const version of ['1.2.3', '1.2.2', '1.1.9']) assert.throws(() => assertVersion(previous, { version, files: { code: 'new' } }), /higher version/);
  for (const version of ['1.2.4', '1.3.0', '2.0.0']) assertVersion(previous, { version, files: { code: 'new' } });
});
