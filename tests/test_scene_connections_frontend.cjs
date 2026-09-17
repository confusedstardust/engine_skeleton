const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('../forge_frontend_next/node_modules/typescript');
const filename = path.resolve(__dirname, '../forge_frontend_next/components/scene-connections.ts');
const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } });
const loaded = new Module(filename);
loaded._compile(compiled.outputText, filename);
const { validateSceneConnections, jumpTarget, isTerminalLine, insertionIndex, keepContinuationLabelsTogether } = loaded.exports;
const narration = { kind: 'narration', text: '内容' };
const jump = target => ({ kind: 'command', text: `changeScene:${target};` });
const scene = (header, lines, marker = 'Scene') => ({ header, lines, marker });

test('repairs legacy missing continuation before authored narration, once, without changing choices or routes', () => {
  const local = { id: 'old-choice', kind: 'choice', text: '', choices: [{ text: '继续', target: 'continue_choice_mu3k9j5e' }, { text: '停一下', target: 'continue_choice_mu3k9j5e' }] };
  const authored = { ...narration, id: 'authored', text: '灯油将尽，老翁又到炭车旁站了一会儿，把明天要带的东西数了一遍。' };
  const exit = { id: 'exit', kind: 'choice', text: '', choices: [{ text: '下一幕', target: 'end.txt' }] };
  const input = [scene('start.txt', [local, authored, exit]), scene('end.txt', [narration], 'Ending')];
  const before = JSON.stringify(input);
  const repaired = loaded.exports.repairContinuationLabels(input);
  assert.equal(JSON.stringify(input), before);
  assert.equal(repaired[0].lines[1].branchLabel, 'continue_choice_mu3k9j5e');
  assert.equal(repaired[0].lines[2], authored);
  assert.equal(repaired[0].lines[0], local);
  assert.equal(repaired[0].lines.at(-1), exit);
  assert.deepEqual(validateSceneConnections(repaired), {});
  assert.deepEqual(loaded.exports.repairContinuationLabels(repaired), repaired);
});

test('does not invent user labels or relocate existing continuation labels', () => {
  const custom = { id: 'custom', kind: 'choice', text: '', choices: [{ text: '自定义', target: 'authored_label' }] };
  const local = { id: 'local', kind: 'choice', text: '', choices: [{ text: '继续', target: 'continue_choice_existing' }] };
  const label = { id: 'label', kind: 'branch', text: 'continue_choice_existing', branchLabel: 'continue_choice_existing' };
  const input = [scene('start.txt', [custom, local, narration, label])];
  assert.deepEqual(loaded.exports.repairContinuationLabels(input), input);
});
test('checks every scene, including inactive ones', () => {
  const errors = validateSceneConnections([scene('start.txt', [jump('a.txt')]), scene('a.txt', [narration]), scene('b.txt', [narration])]);
  assert.deepEqual(Object.keys(errors), ['a.txt', 'b.txt']);
});
test('uses edited connections and accepts implicit ending', () => {
  assert.deepEqual(validateSceneConnections([scene('start.txt', [jump('end.txt')]), scene('end.txt', [narration], 'Ending')]), {});
});
test('every choice target and text must be valid', () => {
  const choice = { kind: 'choice', text: '', choices: [{ text: '继续', target: 'end.txt' }, { text: '缺失', target: 'missing.txt' }] };
  assert.ok(validateSceneConnections([scene('start.txt', [choice]), scene('end.txt', [narration], 'Ending')])['start.txt']);
  choice.choices[1].target = 'end.txt';
  assert.deepEqual(validateSceneConnections([scene('start.txt', [choice]), scene('end.txt', [narration], 'Ending')]), {});
});
test('jump is final, cannot be dialogue text, and must target existing scene', () => {
  assert.equal(jumpTarget({ kind: 'dialogue', text: 'changeScene:end.txt;' }), null);
  assert.equal(isTerminalLine(jump('end.txt')), true);
  const ending = scene('end.txt', [narration], 'Ending');
  assert.ok(validateSceneConnections([scene('start.txt', [jump('end.txt'), narration]), ending])['start.txt']);
  assert.ok(validateSceneConnections([scene('start.txt', [jump('missing.txt')]), ending])['start.txt']);
});
test('local choices alone do not close a scene; following jump does', () => {
  const choice = { kind: 'choice', text: '', choices: [{ text: '互动', target: 'local' }] };
  const label = { kind: 'branch', text: 'local', branchLabel: 'local' };
  const ending = scene('end.txt', [narration], 'Ending');
  assert.ok(validateSceneConnections([scene('start.txt', [choice, label, narration]), ending])['start.txt']);
  assert.deepEqual(validateSceneConnections([scene('start.txt', [choice, label, narration, jump('end.txt')]), ending]), {});
});

test('inserts below selected row, but before final exit', () => {
  const lines = [{ ...narration, id: 'first' }, { ...narration, id: 'second' }, { ...jump('end.txt'), id: 'exit' }];
  assert.equal(insertionIndex(lines, 'first'), 1);
  assert.equal(insertionIndex(lines, 'exit'), 2);
  assert.equal(insertionIndex(lines, null), 2);
  assert.equal(insertionIndex(lines, 'deleted'), 2);
});

test('inserting below local choice includes continuation label; dragging keeps label with choice', () => {
  const choice = { id: 'choice', kind: 'choice', text: '', choices: [{ text: '互动', target: 'continue_choice_local' }] };
  const label = { id: 'choice-label', kind: 'branch', text: 'continue_choice_local', branchLabel: 'continue_choice_local' };
  const first = { ...narration, id: 'first' };
  assert.equal(insertionIndex([choice, label, first], 'choice'), 2);
  assert.deepEqual(keepContinuationLabelsTogether([choice, first, label]).map(line => line.id), ['choice', 'choice-label', 'first']);
});

// Exercise editor event handlers without a browser or additional test dependency.
function editorHarness(lines) {
  const states = [];
  let cursor = 0;
  const hooks = {
    useState(initial) {
      const index = cursor++;
      if (!(index in states)) states[index] = initial;
      return [states[index], value => { states[index] = typeof value === 'function' ? value(states[index]) : value; }];
    },
    useEffect() {}, useMemo: fn => fn(), useRef: value => ({ current: value })
  };
  const sourcePath = path.resolve(__dirname, '../forge_frontend_next/components/laper-scene-workbench.tsx');
  const component = new Module(sourcePath);
  component.paths = Module._nodeModulePaths(path.dirname(sourcePath));
  const originalRequire = component.require.bind(component);
  component.require = name => name === 'react' ? hooks : name === './scene-connections' ? loaded.exports : originalRequire(name);
  component._compile(ts.transpileModule(fs.readFileSync(sourcePath, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX }
  }).outputText, sourcePath);
  const props = {
    mode: 'complete', title: 'test', subtitle: '', plan: null,
    scenes: [{ header: 'start.txt', title: '开场', marker: 'Scene', lines }], activeScene: 0,
    setActiveScene() {}, onScenesChange: scenes => { props.scenes = scenes; }, readonly: false, busy: false,
    routeLabel: () => '', markerLabel: () => '场景', targetOptions: [{ file: 'end.txt', label: '结局' }], inspector: null
  };
  function all(tree, predicate) {
    const result = [];
    function visit(node) {
      if (Array.isArray(node)) return node.forEach(visit);
      if (!node || typeof node !== 'object' || !node.props) return;
      if (predicate(node)) result.push(node);
      visit(node.props.children);
    }
    visit(tree);
    return result;
  }
  function render() { cursor = 0; return component.exports.LaperSceneWorkbench(props); }
  function click(label) {
    const button = all(render(), node => node.type === 'button' && node.props.children === label)[0];
    assert.ok(button, `button ${label} exists`);
    assert.equal(button.props.disabled, false);
    button.props.onClick();
  }
  function select(index) {
    const stack = all(render(), node => node.props.className === 'laper-block-stack laper-line-stack')[0];
    stack.props.onClick({ target: { closest: () => ({ dataset: { laperSceneLineIndex: String(index) } }) } });
  }
  return { props, render, click, select, all };
}

test('toolbar has four consistently styled buttons without redundant add-row action', () => {
  const editor = editorHarness([{ ...narration, id: 'first' }]);
  const buttons = editor.all(editor.render(), node => node.type === 'button' && node.props.className === 'laper-tool accent');
  assert.deepEqual(buttons.map(node => node.props.children), ['旁白', '对话', '互动分支', '场景跳转']);
});

test('selected row is highlighted and consecutive additions insert below selection', () => {
  const editor = editorHarness([{ ...narration, id: 'first' }, { ...narration, id: 'last' }]);
  editor.select(0);
  assert.equal(editor.all(editor.render(), node => node.type === 'article' && node.props['data-selected'] === true).length, 1);
  editor.click('对话');
  assert.equal(editor.props.scenes[0].lines[1].kind, 'dialogue');
  assert.equal(editor.all(editor.render(), node => node.props.role === 'status').length, 0);
  editor.click('旁白');
  assert.equal(editor.props.scenes[0].lines[2].kind, 'narration');
  assert.equal(editor.props.scenes[0].lines[3].id, 'last');
});

test('interactive choice inserts below selection without placeholder narration, supports local continuation for every option', () => {
  const editor = editorHarness([{ ...narration, id: 'first' }, { ...narration, id: 'last' }]);
  editor.select(0);
  editor.click('互动分支');
  const lines = editor.props.scenes[0].lines;
  const addOption = editor.all(editor.render(), node => node.type === 'button' && node.props.children === '添加选项')[0];
  assert.equal(addOption.props.className, 'laper-block-add');
  assert.equal(lines[1].kind, 'choice');
  assert.equal(lines[2].kind, 'branch');
  assert.equal(lines[3].id, 'last');
  assert.equal(editor.all(editor.render(), node => node.type === 'article').length, 3);
  const selects = editor.all(editor.render(), node => node.type === 'select' && node.props['aria-label'] === '跳转场景');
  assert.equal(selects.length, 2);
  for (const select of selects) assert.ok(editor.all(select, node => node.type === 'option' && node.props.children === '留在当前场景（互动后继续）').length);
});

test('duplicate jump gives feedback instead of silently disabling; selected exit stays final', () => {
  const editor = editorHarness([{ ...narration, id: 'first' }]);
  editor.click('场景跳转');
  assert.equal(editor.all(editor.render(), node => node.props.role === 'status').length, 0);
  editor.click('场景跳转');
  assert.equal(editor.props.scenes[0].lines.filter(line => jumpTarget(line)).length, 1);
  const status = editor.all(editor.render(), node => node.props.role === 'status')[0];
  const text = editor.all(status, node => node.props.className === 'laper-editor-notice-text')[0];
  assert.match(text.props.children, /已经添加了场景跳转/);
  assert.equal(editor.all(status, node => node.type === 'svg').length, 1);
  editor.click('对话');
  assert.equal(editor.props.scenes[0].lines[1].kind, 'dialogue');
  assert.equal(jumpTarget(editor.props.scenes[0].lines.at(-1)), 'end.txt');
});

test('existing cross-scene options also offer local continuation and can switch back and forth', () => {
  const editor = editorHarness([{
    id: 'existing', kind: 'choice', text: '', choices: [{ text: '继续', target: 'end.txt', targetSceneFile: 'end.txt' }]
  }]);
  const select = () => editor.all(editor.render(), node => node.type === 'select' && node.props['aria-label'] === '跳转场景')[0];
  const option = editor.all(select(), node => node.type === 'option' && node.props.children === '留在当前场景（互动后继续）')[0];
  assert.ok(option);
  select().props.onChange({ target: { value: option.props.value } });
  assert.equal(editor.props.scenes[0].lines[0].choices[0].targetSceneFile, undefined);
  assert.equal(editor.props.scenes[0].lines[1].kind, 'branch');
  select().props.onChange({ target: { value: 'end.txt' } });
  assert.equal(editor.props.scenes[0].lines.length, 1);
  assert.equal(editor.props.scenes[0].lines[0].choices[0].target_scene_file, 'end.txt');
});
