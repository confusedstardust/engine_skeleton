'use client';

import type { QuizPlan } from '../domain/quiz';
import { Button } from './ui/button';
import { WorkspaceHeading } from './analytics/panel';
import { AnswerCardGrid } from './classroom-answer-cards';

export function ClassroomQuizContent({ quiz, busy, onRegenerate }: { quiz: QuizPlan; busy: boolean; onRegenerate: () => void }) {
  const choices = quiz.questions.filter(q => q.type === 'single_choice').length;
  const judgements = quiz.questions.length - choices;
  return <section className="classroom-manager cq-workspace cq-quiz-content" aria-label="教师习题内容">
    <WorkspaceHeading title="习题内容" meta={`${quiz.questions.length} 道题`}>
      <Button variant="outline" className="cq-button" disabled={busy} onClick={onRegenerate}>{busy ? '正在生成…' : '重新生成题目'}</Button>
    </WorkspaceHeading>
    <section className="cq-context-bar cq-quiz-summary">
      <span className="cq-class-icon" aria-hidden="true">▤</span>
      <div className="cq-quiz-description"><h3>{quiz.title.replace(/课后讲评练|讲评练/g, '课后习题')}</h3><p>{quiz.introduction}</p></div>
      <div className="cq-quiz-types"><span>单选 {choices}</span><span>判断 {judgements}</span></div>
    </section>
    <AnswerCardGrid quiz={quiz} mode="preview" />
  </section>;
}
