const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('../forge_frontend_next/node_modules/typescript');
function load(direction = 'bottom') {
  const filename = path.resolve(__dirname, '../forge_frontend_next/components/scene-scroll-button.tsx');
  const module = new Module(filename);
  module.paths = Module._nodeModulePaths(path.dirname(filename));
  const original = module.require.bind(module);
  let state = 0;
  module.require = name => name === 'react' ? {
    useEffect() {}, useState: () => [state++ === 0 ? direction : state === 2 ? true : 24, () => {}]
  } : original(name);
  module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX }
  }).outputText, filename);
  return module.exports;
}
test('direction is down at top, up at bottom, and follows page half in between', () => {
  const { scrollDirection } = load();
  assert.equal(scrollDirection(0, 2000), 'bottom');
  assert.equal(scrollDirection(1999, 2000), 'top');
  assert.equal(scrollDirection(600, 2000), 'bottom');
  assert.equal(scrollDirection(1500, 2000), 'top');
});
test('desktop button aligns inside inspector; compact screens keep edge placement', () => {
  const { scrollButtonRight } = load();
  assert.equal(scrollButtonRight(1840, 1249), 527);
  assert.equal(1840 - 527 - 48, 1249 + 16);
  assert.equal(scrollButtonRight(1180, 900), 24);
  assert.equal(scrollButtonRight(1840), 24);
});
test('click goes to actual document bottom or top, with accessible labels', () => {
  const savedWindow = global.window;
  const savedDocument = global.document;
  try {
    const calls = [];
    global.document = { scrollingElement: { scrollHeight: 4000 } };
    global.window = { innerHeight: 800, matchMedia: () => ({ matches: false }), scrollTo: args => calls.push(args) };
    let button = load('bottom').SceneScrollButton();
    assert.equal(button.props['aria-label'], '滚动到页面底部');
    button.props.onClick();
    assert.deepEqual(calls.pop(), { top: 3200, behavior: 'smooth' });
    button = load('top').SceneScrollButton();
    assert.equal(button.props['aria-label'], '返回页面顶部');
    global.window.matchMedia = () => ({ matches: true });
    button.props.onClick();
    assert.deepEqual(calls.pop(), { top: 0, behavior: 'auto' });
  } finally {
    global.window = savedWindow;
    global.document = savedDocument;
  }
});
