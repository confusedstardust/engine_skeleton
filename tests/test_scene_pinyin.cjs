const { test } = require('node:test');
const assert = require('node:assert/strict');
const { loadFrontendTs } = require('./helpers/load_frontend_ts.cjs');
const { preparePinyinSelection: prepare, renderPinyinSelection: render, replacePinyinSelection: replace } = loadFrontendTs('forge_frontend_next/lib/scene-pinyin.ts');

test('a selected polyphone uses unselected sentence context', () => {
  const selection = prepare('我去银行办理业务。',3,4);
  assert.equal(selection.characters[0].text,'行');
  assert.equal(selection.characters[0].reading,'háng');
  assert.equal(replace(selection.original,selection,render(selection,['háng'])),'我去银[行](háng)办理业务。');
});
test('inserts per-character ruby, retains punctuation and supports blank readings', () => {
  const source='银行，ABC😀';
  const selection=prepare(source,0,source.length);
  const readings=selection.characters.map(character=>character.reading);
  readings[0]='';
  assert.equal(render(selection,readings),'银[行](háng)，ABC😀');
});
test('existing annotation can be corrected or removed without nested markup', () => {
  const source='我去[银行](yín xíng)。';
  const selection=prepare(source,2,source.length-1);
  assert.equal(render(selection,['yín','háng']),'[银](yín)[行](háng)');
  assert.equal(render(selection,[],true),'银行');
  assert.throws(()=>prepare(source,3,5),/完整选中/);
});
test('author styles survive removal and updating ruby', () => {
  const source='[银行](style=color~red ruby=yín háng)';
  const selection=prepare(source,0,source.length);
  assert.equal(render(selection,[],true),'[银](style=color~red)[行](style=color~red)');
  assert.equal(render(selection,['yín','háng']),'[银](style=color~red ruby=yín)[行](style=color~red ruby=háng)');
});
test('rejects stale edits, multiline selection and syntax injection in readings', () => {
  const selection=prepare('你好',0,2);
  assert.throws(()=>replace('您好',selection,'anything'),/原文已发生变化/);
  assert.throws(()=>prepare('你\n好',0,3),/同一段/);
  assert.throws(()=>render(selection,['nǐ);end;','hǎo']),/格式不正确/);
});

test('existing scene serialization and reload retain annotation text', () => {
  const data=loadFrontendTs('forge_frontend_next/app/jobs/[jobId]/workspace-data.ts');
  const text='我去[银](yín)[行](háng)办理业务。';
  const scenes=[{header:'start.txt',title:'注音',marker:'Scene',lines:[{id:'one',kind:'dialogue',speaker:'小林',rawPrefix:'小林',text}]}];
  const restored=data.parseScenes(data.serializeGameDesignJson(scenes),null);
  assert.equal(restored[0].lines[0].text,text);
});

test('choice text keeps ruby and its target through the existing save format',()=>{
  const data=loadFrontendTs('forge_frontend_next/app/jobs/[jobId]/workspace-data.ts');
  const text='去[银](yín)[行](háng)办理业务';
  const scenes=[{header:'start.txt',title:'选项',marker:'Scene',lines:[{id:'choice',kind:'choice',speaker:'分支',rawPrefix:'choose',text:'',choices:[{text,target:'bank.txt'}]}]}];
  const restored=data.parseScenes(data.serializeGameDesignJson(scenes),null);
  assert.equal(restored[0].lines[0].choices[0].text,text);
  assert.equal(restored[0].lines[0].choices[0].target,'bank.txt');
});
