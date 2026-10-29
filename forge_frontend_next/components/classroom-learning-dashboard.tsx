'use client';
import { LoadingState } from './ui/state';
import { EmptyState } from './ui/state';
import { InlineFeedback } from './ui/feedback';

import { CloseButton } from './ui/close-button';

import { FormSelect } from './ui/form-controls';
import { Button } from './ui/button';

import { useEffect, useId, useState } from 'react';
import { AnalyticsPanel as Panel } from './analytics/panel';
import { MetricCard } from './ui/metric-card';
import { CorrectnessChart, AnswerOverviewChart, QuestionDistributionChart } from './analytics/question-chart';
import type { Analysis, AnalysisResult, AnalysisSnapshot, QuizStatistics } from '../domain/classroom-quiz';

export type DisplayReport = { result: AnalysisResult; snapshot: AnalysisSnapshot; created_at: string; stale: boolean; added_count: number; voided_count: number };
const pct = (n: number | null) => `${Math.round((n ?? 0) * 100)}%`;
const time = (s: string) => new Date(s).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
const EMPTY_QUESTIONS: QuizStatistics['questions'] = [];

export function LearningDashboard({ stats, analysis, report, busy, onAnalyze, onRefresh, refreshing, onExport, onStudent }: { stats: QuizStatistics | null; analysis: Analysis | null; report: DisplayReport | null | undefined; busy: boolean; onAnalyze: () => void; onRefresh: () => void; refreshing: boolean; onExport: () => void; onStudent: (id: string) => void }) {
  const [questionId, setQuestionId] = useState('');
  const [optionId, setOptionId] = useState('');
  const [aiCategory, setAiCategory] = useState('共性误区');
  const graphId = useId();
  const questions = stats?.questions || EMPTY_QUESTIONS;
  const question = questions.find(q => q.id === questionId) || questions[0];
  const questionIndex = questions.findIndex(q => q.id === question?.id);
  const total = questions.reduce((sum, q) => sum + q.total, 0);
  const correct = questions.reduce((sum, q) => sum + q.correct, 0);
  const incorrect = total - correct;
  const rate = total ? correct / total : null;
  const needsReview = questions.filter(q => q.total && q.incorrect / q.total >= .5).length;
  const running = analysis?.status === 'RUNNING' || analysis?.status === 'QUEUED';
  const selectedOption = question?.options.find(o => o.id === optionId);
  const categories = [...new Set(report?.result.items.map(i => i.kind) || [])];
  const selectedCategory = categories.includes(aiCategory) ? aiCategory : categories[0];
  useEffect(() => { setOptionId(''); }, [question?.id]);
  useEffect(() => { if (!questionId && questions.length) setQuestionId(questions[0].id); }, [questionId, questions]);

  if (!stats) return <LoadingState withSpinner className="cq-dashboard-loading">正在加载看板</LoadingState>;

  return <div className="cq-dashboard">
    <div className="cq-dashboard-toolbar"><span className="cq-live-note"><i />{stats.latest_submission ? `最近提交 ${time(stats.latest_submission)}` : '等待学生提交'}</span><div className="cq-actions">
      {report && <Button size="sm" variant="outline" type="button" className="cq-button" disabled={busy} onClick={onExport}><span aria-hidden="true">↓</span>导出分析报告</Button>}
      {analysis && <Button size="sm" variant="outline" busy={refreshing} disabled={busy} onClick={onRefresh}>刷新分析结果</Button>}
      <Button size="sm" variant="primary" type="button" className="cq-button" disabled={busy || !stats.submitted_count || running} onClick={onAnalyze}><span aria-hidden="true">✧</span>{running ? '分析任务已提交' : analysis?.stale || report?.stale ? '更新 AI 分析' : '一键 AI 分析'}</Button>
    </div></div>

    <div className="cq-kpi-grid">
      <MetricCard label="已提交答卷" value={stats.submitted_count} unit="份" caption="当前班级有效答卷" />
      <MetricCard label="习题数量" value={questions.length} unit="题" caption="本次练习题目" />
      <MetricCard label="整体正确率" value={pct(rate)} caption="按全部有效回答统计" />
      <MetricCard label="待讲评题目" value={stats.submitted_count ? needsReview : '—'} unit="题" caption="错误率 ≥ 50%" />
    </div>

    <div className="cq-chart-grid">
      <Panel title="逐题正确率" className="cq-correctness-panel" extra={<span className="cq-panel-caption">{questions.length} 道题</span>}>
        <CorrectnessChart questions={questions} selected={question?.id} onQuestion={id => { setQuestionId(id); setOptionId(''); }} />
      </Panel>
      <Panel title="作答分布" className="cq-distribution-panel"><AnswerOverviewChart correct={correct} incorrect={incorrect} /></Panel>
    </div>

    <Panel title="题目详情" className="cq-question-panel" extra={question && <label className="cq-question-select"><span className="sr-only">选择题目</span><FormSelect ariaLabel="选择题目" value={question.id} onValueChange={value => { setQuestionId(value); setOptionId(''); }} options={questions.map((q, i) => ({ value: q.id, label: `第 ${i + 1} 题` }))} /></label>}>
      {question ? <div className="cq-question-layout"><div className="cq-question-copy"><span className="cq-eyebrow">第 {questionIndex + 1} 题</span><h4>{question.prompt}</h4><div className="cq-question-numbers"><span><strong>{pct(question.correct_rate)}</strong>正确率</span><span><strong>{question.correct}</strong>正确</span><span><strong>{question.incorrect}</strong>错误</span></div></div>
        <div className="cq-option-chart"><div className="cq-option-chart-title">选项分布<span>{question.type === 'judgement' ? '判断题 · 环形图' : '单选题 · 条形图'}</span></div>
          <QuestionDistributionChart question={question} onOption={id => setOptionId(value => value === id ? '' : id)} />
          <div className="cq-option-details">{question.options.map(o => <Button variant="unstyled" type="button" key={o.id} disabled={!o.students?.length} aria-pressed={optionId === o.id} onClick={() => setOptionId(value => value === o.id ? '' : o.id)}><strong>{o.id}</strong><span>{o.text}</span><small>{o.count} 人 · {pct(o.rate)}</small></Button>)}</div>
        {selectedOption && <div className="cq-option-students"><header><strong>选择 {selectedOption.id} 的学生</strong><CloseButton aria-label="收起学生名单" onClick={() => setOptionId('')} /></header><div>{selectedOption.students?.map(s => <Button variant="unstyled" type="button" key={s.id} onClick={() => onStudent(s.id)}>{s.name}<span aria-hidden="true">↗</span></Button>)}</div></div>}
        </div></div> : <EmptyState className="cq-empty">暂无题目</EmptyState>}
    </Panel>

    <Panel title="AI 教学分析" className="cq-ai-panel" extra={<span className={`cq-analysis-state ${report?.stale ? 'is-stale' : ''}`}>{running ? '分析中' : report ? report.stale ? '待更新' : '已生成' : '未生成'}</span>}>
      {analysis?.status === 'FAILED' && <InlineFeedback  className="cq-inline-feedback">{analysis.error || '分析暂时失败，请重试'}</InlineFeedback>}
      {report?.stale && <p className="cq-feedback">报告生成后新增 {report.added_count} 份、作废 {report.voided_count} 份答卷，请更新分析。</p>}
      {report ? <>
        <div className="cq-ai-overview"><span className="cq-ai-mark" aria-hidden="true">✧</span><div><div className="cq-ai-meta">基于 {report.snapshot.attempt_ids.length} 份答卷 · {time(report.created_at)}{report.snapshot.attempt_ids.length < 5 ? ' · 样本较少' : ''}</div><p>{report.result.overview}</p></div></div>
        <div className="cq-ai-tabs" role="tablist" aria-label="分析类别">{categories.map(kind => <Button variant="unstyled" type="button" role="tab" aria-selected={selectedCategory === kind} id={`${graphId}-tab-${kind}`} aria-controls={`${graphId}-analysis-content`} key={kind} onClick={() => setAiCategory(kind)} onKeyDown={event => {
          if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
          const i = categories.indexOf(kind); const next = categories[(i + (event.key === 'ArrowRight' ? 1 : -1) + categories.length) % categories.length];
          setAiCategory(next); document.getElementById(`${graphId}-tab-${next}`)?.focus();
        }}>{kind}</Button>)}</div>
        <div role="tabpanel" id={`${graphId}-analysis-content`} aria-labelledby={`${graphId}-tab-${selectedCategory}`} className="cq-ai-items">{report.result.items.filter(item => item.kind === selectedCategory).map((item, i) => <article key={`${selectedCategory}-${i}`}><p>{item.text}</p><div className="cq-evidence-list">{item.question_ids.map(id => {
          const evidence = report.snapshot.statistics.questions.find(q => q.id === id); const index = report.snapshot.quiz.questions.findIndex(q => q.id === id);
          return evidence ? <Button variant="unstyled" type="button" key={id} onClick={() => { setQuestionId(id); setOptionId(''); document.querySelector('.cq-question-panel')?.scrollIntoView({ behavior: 'smooth', block: 'center' }); }}>第 {index + 1} 题<span>正确率 {pct(evidence.correct_rate)}</span><span aria-hidden="true">↗</span></Button> : null;
        })}</div></article>)}</div>
      </> : <EmptyState className="cq-ai-empty"><span aria-hidden="true">✧</span><h4>{running ? '分析任务已提交' : '生成本次练习的教学分析'}</h4><p>{running ? '稍后点击“刷新分析结果”查看，无需保持本页打开。' : stats.submitted_count ? '查看共性误区、讲评重点与教学建议' : '收到学生答卷后即可生成分析'}</p></EmptyState>}
    </Panel>
  </div>;
}
