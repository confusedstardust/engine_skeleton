import type { Attempt, StudentQuestion } from '../domain/classroom-quiz';
import type { QuizPlan } from '../domain/quiz';

export function AnswerCard({ question, answer, index, preview = false }: { question: StudentQuestion; answer?: Attempt['answers'][string]; index: number; preview?: boolean }) {
  const correct = Boolean(answer?.is_correct);
  return <article className={`classroom-answer-card ${preview ? 'is-preview' : correct ? 'is-correct' : 'is-incorrect'}`}>
    <header><span className="classroom-answer-number">{String(index + 1).padStart(2, '0')}</span><span className="classroom-answer-type">{question.type === 'judgement' ? '判断题' : '单选题'}</span><span className="classroom-answer-result">{preview ? `答案 ${question.correct_option_ids?.join('、') || '—'}` : <><span aria-hidden="true">{correct ? '✓' : '×'}</span>{correct ? '正确' : '错误'}</>}</span></header>
    <h3>{question.prompt}</h3>
    <ul className="classroom-answer-options">{question.options.map(option => {
      const selected = preview ? question.correct_option_ids?.includes(option.id) : answer?.selected_option_id === option.id;
      return <li key={option.id} className={selected ? 'is-selected' : undefined} aria-label={selected ? `${option.id} ${option.text}，${preview ? '正确选项' : '已选'}` : undefined}><span>{option.id}</span><p>{option.text}</p></li>;
    })}</ul>
  </article>;
}

export function AnswerCardGrid(props: { attempt: Attempt; mode?: 'answer' } | { quiz: QuizPlan; mode: 'preview' }) {
  const questions = props.mode === 'preview' ? props.quiz.questions : props.attempt.quiz.questions;
  return <div className="classroom-answer-grid">{questions.map((question, index) => <AnswerCard key={question.id} question={question} answer={props.mode === 'preview' ? undefined : props.attempt.answers[question.id]} index={index} preview={props.mode === 'preview'} />)}</div>;
}
