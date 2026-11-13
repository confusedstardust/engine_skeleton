const test = require('node:test');
const assert = require('node:assert/strict');
const { renderToStaticMarkup } = require('../forge_frontend_next/node_modules/react-dom/server');
const { loadFrontendTs } = require('./helpers/load_frontend_ts.cjs');
const { QuestionCard, QuestionOptions, QuestionExplanation } = loadFrontendTs('forge_frontend_next/components/quiz-question.tsx');
const question = { id: 'q1', type: 'single_choice', prompt: '共同题干', options: [{ id: 'A', text: '正确选项' }, { id: 'B', text: '干扰项' }], correct_option_ids: ['A'], explanation: '答案依据' };

test('shared options hide correctness until revealed and preserve selection callback', () => {
  let selected;
  const tree = QuestionOptions({ question, selected: 'B', onSelect: id => { selected = id; } });
  const markup = renderToStaticMarkup(tree);
  assert.match(markup, /role="radiogroup"/);
  assert.doesNotMatch(markup, /class="[^"]*\b(correct|wrong)\b/);
  tree.props.children[0].props.onClick();
  assert.equal(selected, 'A');
  const revealed = renderToStaticMarkup(QuestionOptions({ question, selected: 'B', revealed: true, disabled: true }));
  assert.match(revealed, /class="correct"/);
  assert.match(revealed, /class="selected wrong"/);
  assert.equal((revealed.match(/disabled=""/g) || []).length, 2);
});

test('teacher options share selection and preserve inline editing', () => {
  let changed;
  const tree = QuestionOptions({ question, variant: 'answer', revealed: true, onEdit: patch => { changed = patch; } });
  const option = tree.props.children[1];
  const controls = option.props.children[1].props.children;
  controls[1].props.onChange();
  assert.deepEqual(changed, { correct_option_ids: ['B'] });
  controls[0].props.onChange({ target: { value: '修改后的选项' } });
  assert.deepEqual(changed.options, [{ id: 'A', text: '正确选项' }, { id: 'B', text: '修改后的选项' }]);
  const locked = renderToStaticMarkup(QuestionOptions({ question, variant: 'answer', selected: 'B' }));
  assert.match(locked, /class="is-selected" aria-label="B 干扰项，已选"/);
});

test('card variants retain their anchors and explanation uses server correctness', () => {
  const practice = renderToStaticMarkup(QuestionCard({ question, index: 0, id: 'question-q1', children: '内容' }));
  assert.match(practice, /id="question-q1"/);
  assert.match(practice, /<h2>共同题干<\/h2>/);
  const teacher = renderToStaticMarkup(QuestionCard({ question, index: 0, variant: 'answer', tone: 'correct', result: '正确', children: '内容' }));
  assert.match(teacher, /classroom-answer-card is-correct/);
  assert.match(teacher, /<h3>共同题干<\/h3>/);
  assert.match(renderToStaticMarkup(QuestionExplanation({ question, selected: 'A', correct: false })), /回答错误/);
});

test('loading states include an animation by default with an explicit text-only escape', () => {
  const { LoadingState } = loadFrontendTs('forge_frontend_next/components/ui/state.tsx');
  assert.match(renderToStaticMarkup(LoadingState({ children: '正在加载' })), /pending-spinner/);
  assert.doesNotMatch(renderToStaticMarkup(LoadingState({ children: '正在加载', withSpinner: false })), /pending-spinner/);
});
