const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { loadFrontendTs } = require('./helpers/load_frontend_ts.cjs');
const data = loadFrontendTs(path.resolve(__dirname, '../forge_frontend_next/app/jobs/[jobId]/workspace-data.ts'));
const { validateSceneConnections } = loadFrontendTs(path.resolve(__dirname, '../forge_frontend_next/components/scene-connections.ts'));

function scenes() {
  return [{ header: 'start.txt', title: '开始', lines: [
    { id: 'pick', kind: 'choice', text: '', choices: [
      { id: 'stay', text: '留下', target: 'continue_choice_main', response_lines: [{ id: 'response1', kind: 'dialogue', speaker: '甲', text: '回应', rawPrefix: '' }] },
      { id: 'leave', text: '离开', target: 'end.txt', response_lines: [] }
    ] },
    { id: 'common', kind: 'narration', speaker: '旁白', text: '公共正文', rawPrefix: '旁白' },
    { id: 'exit', kind: 'command', text: 'changeScene:end.txt;', rawPrefix: 'changeScene' }
  ] }, { header: 'end.txt', title: '结束', marker: 'Ending', lines: [] }];
}

test('option response IDs and text survive save, reload, rename and option reorder', () => {
  const restored = data.parseScenes(data.serializeGameDesignJson(scenes()), null);
  const options = restored[0].lines[0].choices;
  options.reverse(); options[1].text = '改名';
  const again = data.parseScenes(data.serializeGameDesignJson(restored), null);
  assert.equal(again[0].lines[0].choices[1].id, 'stay');
  assert.equal(again[0].lines[0].choices[1].response_lines[0].text, '回应');
  assert.equal(again[0].lines[0].choices[1].response_lines[0].id, 'response1');
  assert.deepEqual(validateSceneConnections(again), {});
});

test('blank or unsupported responses identify the option in connection errors', () => {
  const restored = data.parseScenes(data.serializeGameDesignJson(scenes()), null);
  restored[0].lines[0].choices[0].response_lines[0].text = '';
  assert.match(validateSceneConnections(restored)['start.txt'], /留下.*第 1 句/);
});
