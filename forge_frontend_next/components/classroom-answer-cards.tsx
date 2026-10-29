import type { Attempt, StudentQuestion } from '../domain/classroom-quiz';
import type { QuizPlan, QuizQuestion } from '../domain/quiz';
import { QuestionCard, QuestionOptions } from './quiz-question';
import { FormSelect } from './ui/form-controls';

export function AnswerCard({ question, answer, index, preview = false, onChange, disabled }: { question: StudentQuestion; answer?: Attempt['answers'][string]; index: number; preview?: boolean; onChange?: (patch: Partial<QuizQuestion>) => void; disabled?: boolean }) {
  const correct = Boolean(answer?.is_correct);
  return <QuestionCard question={question} index={index} variant="answer" tone={preview ? 'preview' : correct ? 'correct' : 'incorrect'}
    result={preview ? `答案 ${question.correct_option_ids?.join('、') || '—'}` : <><span aria-hidden="true">{correct ? '✓' : '×'}</span>{correct ? '正确' : '错误'}</>}
    prompt={onChange ? <textarea className="cq-inline-field cq-prompt-field" aria-label={`第 ${index + 1} 题题干`} required maxLength={300} disabled={disabled} value={question.prompt} onChange={e => onChange({ prompt: e.target.value })} /> : undefined}>
    <QuestionOptions question={question} index={index} variant="answer" selected={preview ? undefined : answer?.selected_option_id} revealed={preview} disabled={disabled} onEdit={onChange} />
    {onChange && <details className="cq-card-details"><summary>答案解析与教学信息</summary><div>
      <label>答案解析<textarea className="cq-inline-field" required maxLength={600} disabled={disabled} value={question.explanation || ''} onChange={e => onChange({ explanation: e.target.value })} /></label>
      <div className="cq-card-metadata"><label>知识点<input className="cq-inline-field" required maxLength={120} disabled={disabled} value={question.knowledge_point || ''} onChange={e => onChange({ knowledge_point: e.target.value })} /></label>
      <label>难度<FormSelect ariaLabel={`第 ${index + 1} 题难度`} value={question.difficulty || '基础'} disabled={disabled} options={['基础', '进阶', '挑战'].map(value => ({ value, label: value }))} onValueChange={value => onChange({ difficulty: value as QuizQuestion['difficulty'] })} /></label></div>
      <label>教学提示<textarea className="cq-inline-field" required maxLength={400} disabled={disabled} value={question.teaching_tip || ''} onChange={e => onChange({ teaching_tip: e.target.value })} /></label>
    </div></details>}
  </QuestionCard>;
}

export function AnswerCardGrid(props: { attempt: Attempt; mode?: 'answer' } | { quiz: QuizPlan; mode: 'preview'; onChange?: (index: number, patch: Partial<QuizQuestion>) => void; disabled?: boolean }) {
  const questions = props.mode === 'preview' ? props.quiz.questions : props.attempt.quiz.questions;
  return <div className="classroom-answer-grid">{questions.map((question, index) => <AnswerCard key={question.id} question={question} answer={props.mode === 'preview' ? undefined : props.attempt.answers[question.id]} index={index} preview={props.mode === 'preview'} onChange={props.mode === 'preview' && props.onChange ? patch => props.onChange?.(index, patch) : undefined} disabled={props.mode === 'preview' ? props.disabled : undefined} />)}</div>;
}
