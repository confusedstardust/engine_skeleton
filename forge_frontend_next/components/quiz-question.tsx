'use client';

import type { ReactNode } from 'react';
import type { QuizQuestion } from '../domain/quiz';
import { Button } from './ui/button';

type Question = Pick<QuizQuestion, 'id' | 'type' | 'prompt' | 'options'> & Partial<QuizQuestion>;

export function QuestionCard({ question, index, variant = 'practice', tone = 'preview', id, typeLabel, prompt, result, children }: {
  question: Question; index: number; variant?: 'practice' | 'answer'; tone?: 'preview' | 'correct' | 'incorrect';
  id?: string; typeLabel?: string; prompt?: ReactNode; result?: ReactNode; children: ReactNode;
}) {
  const answer = variant === 'answer';
  const label = typeLabel || (question.type === 'judgement' ? '判断题' : '单选题');
  const Heading = answer ? 'h3' : 'h2';
  return <article id={id} className={answer ? `classroom-answer-card is-${tone}` : `quiz-card ${question.type === 'judgement' ? 'judgement' : 'choice'}`}>
    <header><span className={answer ? 'classroom-answer-number' : undefined}>{String(index + 1).padStart(2, '0')}</span>
      {answer ? <span className="classroom-answer-type">{label}</span> : <em>{label}</em>}
      {result && <span className="classroom-answer-result">{result}</span>}
    </header>
    <Heading>{prompt ?? question.prompt}</Heading>
    {children}
  </article>;
}

export function QuestionOptions({ question, selected, revealed = false, disabled, variant = 'practice', onSelect, onEdit, index = 0 }: {
  question: Question; selected?: string; revealed?: boolean; disabled?: boolean; variant?: 'practice' | 'answer';
  onSelect?: (id: string) => void; onEdit?: (patch: Partial<QuizQuestion>) => void; index?: number;
}) {
  const correctIds = revealed ? question.correct_option_ids || [] : [];
  if (variant === 'answer') return <ul className="classroom-answer-options">{question.options.map(option => {
    const active = selected ? selected === option.id : correctIds.includes(option.id);
    return <li key={option.id} className={active ? 'is-selected' : undefined} aria-label={active ? `${option.id} ${option.text}，${selected ? '已选' : '正确选项'}` : undefined}>
      <span>{option.id}</span>
      {onEdit ? <><textarea className="cq-inline-field cq-option-field" aria-label={`第 ${index + 1} 题选项 ${option.id}`} required maxLength={180} readOnly={question.type === 'judgement'} disabled={disabled} value={option.text}
        onChange={e => onEdit({ options: question.options.map(o => o.id === option.id ? { ...o, text: e.target.value } : o) })} />
        <input className="cq-correct-radio" type="radio" name={`correct-${question.id}`} aria-label={`第 ${index + 1} 题正确答案 ${option.id}`} title="设为正确答案" disabled={disabled} checked={active} onChange={() => onEdit({ correct_option_ids: [option.id] })} /></> : <p>{option.text}</p>}
    </li>;
  })}</ul>;
  return <div className="quiz-options" role="radiogroup" aria-label={question.prompt}>{question.options.map(option => {
    const active = selected === option.id;
    return <Button variant="unstyled" key={option.id} type="button" role="radio" aria-checked={active} disabled={disabled}
      className={[active && 'selected', correctIds.includes(option.id) && 'correct', revealed && active && !correctIds.includes(option.id) && 'wrong'].filter(Boolean).join(' ')}
      onClick={() => onSelect?.(option.id)}><span>{option.id}</span><strong>{option.text}</strong></Button>;
  })}</div>;
}

export function QuestionExplanation({ question, selected, correct, announce = false }: { question: Question; selected?: string; correct?: boolean; announce?: boolean }) {
  const isCorrect = correct ?? Boolean(selected && question.correct_option_ids?.includes(selected));
  return <div className="quiz-explanation" role={announce ? 'status' : undefined}>
    <strong>{isCorrect ? '回答正确' : `回答错误，正确答案：${question.correct_option_ids?.join('、') || '—'}`}</strong><p>{question.explanation}</p>
  </div>;
}
