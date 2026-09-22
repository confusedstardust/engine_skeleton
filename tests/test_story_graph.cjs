const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('../forge_frontend_next/node_modules/typescript');
const filename = path.resolve(__dirname, '../forge_frontend_next/components/story-graph-data.ts');
const loaded = new Module(filename);
loaded._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText, filename);
const { planningGraph, readingNodeIds, relatedNodeIds, returnEdgeIds, primaryRouteEdgeIds, compactStoryPositions, nearestCardHandles } = loaded.exports;
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
test('reading focus starts with three scenes and node focus includes direct context', () => {
  const graph = { nodes: ['a', 'b', 'c', 'd'].map(id => ({ id })), edges: [
    { source: 'a', target: 'b' }, { source: 'b', target: 'c' }, { source: 'b', target: 'd' }
  ] };
  assert.deepEqual(readingNodeIds(graph), ['a', 'b', 'c']);
  assert.deepEqual(relatedNodeIds(graph, 'b'), ['b', 'a', 'c', 'd']);
});
test('marks only the arrows that return to an active story path', () => {
  const graph = { nodes: ['a', 'b', 'c', 'd'].map(id => ({ id })), edges: [
    { id: 'ab', source: 'a', target: 'b' },
    { id: 'bc', source: 'b', target: 'c' },
    { id: 'ca', source: 'c', target: 'a' },
    { id: 'cd', source: 'c', target: 'd' },
    { id: 'dd', source: 'd', target: 'd' }
  ] };
  assert.deepEqual([...returnEdgeIds(graph)], ['ca', 'dd']);
  assert.deepEqual([...primaryRouteEdgeIds(graph, returnEdgeIds(graph))], ['ab', 'bc', 'cd']);
});
test('compact layout folds a long story into alternating rows', () => {
  const nodes = Array.from({ length: 11 }, (_, index) => ({ id: `n${index}`, kind: index ? 'scene' : 'start' }));
  const edges = nodes.slice(1).map((node, index) => ({ id: `e${index}`, source: `n${index}`, target: node.id }));
  const positions = compactStoryPositions({ nodes, edges });
  assert.deepEqual(positions.get('n0'), { x: 0, y: 0, order: 1 });
  assert.deepEqual(positions.get('n3'), { x: 960, y: 0, order: 4 });
  assert.deepEqual(positions.get('n4'), { x: 960, y: 220, order: 5 });
  assert.deepEqual(positions.get('n7'), { x: 0, y: 220, order: 8 });
  assert.deepEqual(positions.get('n10'), { x: 640, y: 440, order: 11 });
});
test('compact layout follows story routes instead of filename order', () => {
  const nodes = [
    { id: 'start', kind: 'start' }, { id: 'c', kind: 'scene' },
    { id: 'a', kind: 'scene' }, { id: 'b', kind: 'scene' }
  ];
  const edges = [
    { id: 'sa', source: 'start', target: 'a' },
    { id: 'ab', source: 'a', target: 'b' },
    { id: 'bc', source: 'b', target: 'c' }
  ];
  const positions = compactStoryPositions({ nodes, edges });
  assert.equal(positions.get('start').order, 1);
  assert.equal(positions.get('a').order, 2);
  assert.equal(positions.get('b').order, 3);
  assert.equal(positions.get('c').order, 4);
});
test('edge handles follow the nearest card sides after nodes move', () => {
  assert.deepEqual(nearestCardHandles({ x: 0, y: 0 }, { x: 320, y: 0 }), { sourceHandle: 'source-right', targetHandle: 'target-left' });
  assert.deepEqual(nearestCardHandles({ x: 0, y: 0 }, { x: 100, y: 220 }), { sourceHandle: 'source-bottom', targetHandle: 'target-top' });
  assert.deepEqual(nearestCardHandles({ x: 320, y: 220 }, { x: 0, y: 220 }), { sourceHandle: 'source-left', targetHandle: 'target-right' });
  assert.deepEqual(nearestCardHandles({ x: 0, y: 220 }, { x: 0, y: 0 }), { sourceHandle: 'source-top', targetHandle: 'target-bottom' });
});
