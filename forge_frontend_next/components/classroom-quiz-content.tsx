'use client';

import { useState, type ReactNode } from 'react';
import type { QuizPlan, QuizQuestion } from '../domain/quiz';
import { Button } from './ui/button';
import { InlineFeedback } from './ui/feedback';
import { WorkspaceHeading } from './analytics/panel';
import { AnswerCardGrid } from './classroom-answer-cards';

export function ClassroomQuizContent({ quiz, busy, onRegenerate, onSave, onEditingChange, generationControls }: {
  quiz: QuizPlan; busy: boolean; onRegenerate: () => void; onSave: (quiz: QuizPlan) => Promise<void>;
  onEditingChange: (editing: boolean) => void; generationControls?: ReactNode;
}) {
  const [draft, setDraft] = useState<QuizPlan | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  function updateQuestion(index: number, patch: Partial<QuizQuestion>) {
    setDraft(value => value && ({ ...value, questions: value.questions.map((q, i) => i === index ? { ...q, ...patch } : q) }));
  }
  function finish() { setDraft(null); setError(''); onEditingChange(false); }
  async function save() {
    if (!draft) return;
    setSaving(true); setError('');
    try { await onSave(draft); finish(); }
    catch (e) { setError(e instanceof Error ? e.message : '保存失败，请重试'); }
    finally { setSaving(false); }
  }
  const displayed = draft || quiz;
  const choices = displayed.questions.filter(q => q.type === 'single_choice').length;
  const judgements = displayed.questions.length - choices;
  return <section className={`classroom-manager cq-workspace cq-quiz-content ${draft ? 'is-editing' : ''}`} aria-label="教师习题内容">
    <form onSubmit={event => { event.preventDefault(); void save(); }} onInvalidCapture={event => { const details = (event.target as HTMLElement).closest('details'); if (details) details.open = true; }}>
      <WorkspaceHeading title="习题内容" meta={`${displayed.questions.length} 道题`}>
        <div className="cq-quiz-actions">
          {draft ? <><span className="cq-editing-label"><i />编辑中</span><Button size="sm" className="cq-button" disabled={saving || busy} onClick={finish}>取消</Button><Button size="sm" variant="primary" className="cq-button" type="submit" busy={saving} disabled={busy}>{saving ? '正在保存…' : '保存修改'}</Button></> : <>
            <Button size="sm" variant="outline" className="cq-button" disabled={busy} onClick={() => { setDraft(structuredClone(quiz)); onEditingChange(true); }}>编辑习题</Button>
            <div className="cq-regenerate-actions">{generationControls}<Button size="sm" variant="outline" className="cq-button" disabled={busy} onClick={onRegenerate}>{busy ? '正在生成…' : '重新生成题目'}</Button></div>
          </>}
        </div>
      </WorkspaceHeading>
      {error && <InlineFeedback>{error}</InlineFeedback>}
      {draft && <p className="cq-inline-edit-note">直接修改卡片内容，勾选选项右侧圆点设置正确答案。保存后用于后续分享，已发放的练习保留原题。</p>}
      <section className="cq-context-bar cq-quiz-summary">
        <span className="cq-class-icon" aria-hidden="true">▤</span>
        <div className="cq-quiz-description"><h3>{draft ? <input className="cq-inline-field cq-title-field" aria-label="习题标题" required maxLength={120} disabled={saving || busy} value={draft.title} onChange={e => setDraft({ ...draft, title: e.target.value })} /> : quiz.title.replace(/课后讲评练|讲评练/g, '课后习题')}</h3>
          {draft ? <textarea className="cq-inline-field cq-introduction-field" aria-label="习题说明" required maxLength={300} disabled={saving || busy} value={draft.introduction} onChange={e => setDraft({ ...draft, introduction: e.target.value })} /> : <p>{quiz.introduction}</p>}
        </div>
        <div className="cq-quiz-types"><span>单选 {choices}</span><span>判断 {judgements}</span></div>
      </section>
      <AnswerCardGrid quiz={displayed} mode="preview" onChange={draft ? updateQuestion : undefined} disabled={saving || busy} />
    </form>
  </section>;
}
