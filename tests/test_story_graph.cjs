const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('../forge_frontend_next/node_modules/typescript');
const filename = path.resolve(__dirname, '../forge_frontend_next/components/story-graph-data.ts');
const loaded = new Module(filename);
loaded._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText, filename);
const { planningGraph } = loaded.exports;
test('reads chained routes and ending aliases without inventing connections', () => {
  const graph = planningGraph({ story_progression: [{ id: 'start', name: '入山' }, { id: 'phase1', name: '选择' }], endings: [{ ending_type: 'true ending' }], narrative_structure: 'graph TD\nstart[入山] --> phase1[选择] -->|回家|ending_true[结局]' });
  assert.equal(graph.nodes.length, 3);
  assert.equal(graph.edges.length, 2);
  assert.equal(graph.edges[1].target, 'ending_1');
  assert.equal(graph.edges[1].label, '回家');
});
test('missing routes are not guessed from scene order', () => {
  const graph = planningGraph({ story_progression: [{ id: 'start', name: '入山' }], endings: [], narrative_structure: 'graph TD' });
  assert.equal(graph.edges.length, 0);
  assert.equal(graph.warnings.length, 1);
});
