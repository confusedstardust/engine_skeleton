const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { loadFrontendTs } = require('./helpers/load_frontend_ts.cjs');
const data = loadFrontendTs(path.resolve(__dirname, '../forge_frontend_next/app/jobs/[jobId]/workspace-data.ts'));

test('plan parsing keeps music metadata and handles absent or malformed artifacts', () => {
  const plan = data.parsePlan(JSON.stringify({ title: '测试', story_progression: [{ id: 'p1', music_mood: 'warm' }], endings: [{ ending_type: '好结局', music_mood: 'happy' }] }));
  assert.equal(plan.story_progression[0].music_mood, 'warm');
  assert.equal(plan.endings[0].music_mood, 'happy');
  assert.deepEqual(plan.characters, []);
  assert.equal(data.parsePlan(null), null);
  assert.equal(data.parsePlan('{'), null);
});

test('text scenes preserve label commands, local continuation and cross-scene choices', () => {
  const scenes = data.parseScenes('Scene:start.txt\n旁白:开场;\nchoose:继续:continue_choice_test|结束:end.txt;\nlabel:continue_choice_test;\n角色:继续说话;\nchangeScene:end.txt;\nEnding:end.txt\n旁白:结束; ', null);
  assert.equal(scenes.length, 2);
  const lines = scenes[0].lines;
  assert.equal(lines[1].kind, 'choice');
  assert.equal(lines[1].choices[0].target, 'continue_choice_test');
  assert.equal(lines[2].kind, 'branch');
  assert.equal(lines[2].branchLabel, 'continue_choice_test');
  assert.equal(lines[3].text, '继续说话');
  assert.equal(lines[4].kind, 'command');
});

test('JSON serialization repairs legacy continuation once and preserves authored lines on round trip', () => {
  const scenes = [{ header: 'start.txt', title: '开场', marker: 'Scene', lines: [
    { id: 'choice', kind: 'choice', speaker: '分支', rawPrefix: 'choose', text: '', choices: [{ text: '继续', target: 'continue_choice_test' }] },
    { id: 'authored', kind: 'narration', speaker: '旁白', rawPrefix: '旁白', text: '作者原文' },
  ] }];
  const serialized = data.serializeGameDesignJson(scenes);
  const restored = data.parseScenes(serialized, null);
  assert.equal(restored[0].lines.filter(line => line.branchLabel === 'continue_choice_test').length, 1);
  assert.equal(restored[0].lines.at(-1).text, '作者原文');
  assert.deepEqual(JSON.parse(data.serializeGameDesignJson(restored)), JSON.parse(serialized));
  assert.equal(scenes[0].lines.length, 2);
});

test('scene plan metadata remains available to draft and completed scene parsing', () => {
  const plan = data.parsePlan(JSON.stringify({ story_progression: [{ id: 'phase1', name: '开始', strtype: 'branch' }] }));
  const scenePlan = data.parseScenePlan(JSON.stringify({ scenes: [{ scene_file: 'start.txt', source_node: 'phase1', node_name: '开始', strtype: 'branch' }], endings: [] }));
  const draft = data.parseGameDesignDraft('Scene:start.txt\n旁白:开始;', plan, scenePlan);
  const completed = data.parseScenes('Scene:start.txt\n旁白:开始;', plan, null, scenePlan);
  assert.equal(draft[0].sourceNode, 'phase1');
  assert.equal(completed[0].sourceNode, 'phase1');
  assert.equal(completed[0].strtype, 'branch');
});

test('connection report rejects malformed payloads', () => {
  const report = { status: 'passed', reachable: ['start.txt'], fixes: [], errors: [] };
  assert.deepEqual(data.parseSceneConnectionReport(JSON.stringify(report)), report);
  assert.equal(data.parseSceneConnectionReport('{}'), null);
  assert.equal(data.parseSceneConnectionReport('not json'), null);
});
