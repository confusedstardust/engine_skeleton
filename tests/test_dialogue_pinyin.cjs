const { test } = require('node:test');
const assert = require('node:assert/strict');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const { loadFrontendTs } = require('./helpers/load_frontend_ts.cjs');
const { addDialoguePinyin } = loadFrontendTs('src/Stage/TextBox/dialoguePinyin.tsx');
const nodes = text => Array.from(text, char => ({ reactNode: char, plainText: char }));
const html = lines => renderToStaticMarkup(React.createElement('div', null, lines.flat().map((node,i) => React.createElement('span', {key:i},node.reactNode))));

test('uses phrase context across styled nodes and leaves punctuation, Latin text and emoji unannotated', () => {
  const line = nodes('银行ABC，😀行走');
  line[1].reactNode = React.createElement('span', {className:'styled'}, '行');
  const output = html(addDialoguePinyin([line]));
  assert.match(output, /háng/);
  assert.match(output, /xíng/);
  assert.match(output, /class="styled"/);
  assert.equal((output.match(/<rt>/g)||[]).length, 4);
  assert.ok(output.includes('😀'));
  assert.equal(line[1].plainText,'行');
});

test('retains author supplied ruby and keeps subsequent readings aligned', () => {
  const manual = {plainText:'重庆',manualRuby:true,reactNode:React.createElement('ruby', null,'重庆',React.createElement('rt',null,'custom'))};
  const result = addDialoguePinyin([[manual,...nodes('银行')]]);
  assert.equal(result[0][0],manual);
  const output = html(result);
  assert.match(output, /custom/);
  assert.match(output, /háng/);
  assert.equal((output.match(/<rt>/g)||[]).length,3);
});
