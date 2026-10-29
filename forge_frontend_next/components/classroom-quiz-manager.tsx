'use client';
import { LoadingState } from './ui/state';
import { InlineFeedback } from './ui/feedback';
import { EmptyState } from './ui/state';

import { DialogHeader } from './ui/dialog-header';

import { FormSelect } from './ui/form-controls';
import { Button } from './ui/button';
import './classroom-quiz.css';

import { useCallback, useEffect, useRef, useState } from 'react';
import { forgeApi as api } from '../lib/api-client';
import type { Analysis, Assignment, Attempt, QuizStatistics, ShareLink, Submission } from '../domain/classroom-quiz';
import * as Dialog from './ui/dialog';
import { AssignmentPicker, assignmentTime } from './classroom-assignment-picker';
import { LearningDashboard } from './classroom-learning-dashboard';
import { AnswerCardGrid } from './classroom-answer-cards';
import { SubmissionTable } from './classroom-submission-table';
import { WorkspaceHeading } from './analytics/panel';
import { useConfirmation } from './ui/modal';
import { useToast } from './ui/toast';

const percent = (value: number | null) => value === null ? '暂无数据' : `${Math.round(value * 100)}%`;
const date = (value: string) => new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' });
function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function ClassroomQuizManager({ jobId, quizTitle, view }: { jobId: string; quizTitle: string; view?: 'submissions' | 'analysis' }) {
  const [tab, setTab] = useState<'submissions' | 'analysis'>('submissions');
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [classes, setClasses] = useState<{ id: string; name: string }[]>([]);
  const [selected, setSelected] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [newRound, setNewRound] = useState(false);
  const [classId, setClassId] = useState('');
  const [className, setClassName] = useState('');
  const [title, setTitle] = useState(quizTitle);
  const [share, setShare] = useState<ShareLink | null>(null);
  const [qr, setQr] = useState('');
  const [qrError, setQrError] = useState('');
  const [links, setLinks] = useState<{ id: string; created_at: string; revoked_at: string | null }[]>([]);
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [stats, setStats] = useState<QuizStatistics | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [detail, setDetail] = useState<Attempt | null>(null);
  const [reason, setReason] = useState('');
  const [query, setQuery] = useState('');
  const [order, setOrder] = useState('latest');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [ready, setReady] = useState(false);
  const shareRef = useRef<HTMLDivElement>(null);
  const activeSelection = useRef('');
  const notify = useToast(); const confirm = useConfirmation();
  const assignment = assignments.find(a => a.id === selected);
  useEffect(() => { if (view) setTab(view); }, [view]);

  const refreshList = useCallback(async (signal?: AbortSignal) => {
    const [a, c] = await Promise.all([api<{ assignments: Assignment[] }>(`/jobs/${jobId}/quiz/assignments`, { signal }), api<{ classes: { id: string; name: string }[] }>('/quiz/classes', { signal })]);
    if (signal?.aborted) return;
    setAssignments(a.assignments); setClasses(c.classes); setSelected(value => a.assignments.some(item => item.id === value) ? value : a.assignments.find(item => item.submitted_count > 0)?.id || a.assignments[0]?.id || ''); setReady(true);
  }, [jobId]);

  const refreshDetail = useCallback(async (aid: string, signal?: AbortSignal) => {
    const [s, t, a, l] = await Promise.all([
      api<{ submissions: Submission[] }>(`/quiz/assignments/${aid}/submissions`, { signal }),
      api<QuizStatistics>(`/quiz/assignments/${aid}/statistics`, { signal }),
      api<{ analysis: Analysis | null }>(`/quiz/assignments/${aid}/analyses/latest`, { signal }),
      api<{ links: { id: string; created_at: string; revoked_at: string | null }[] }>(`/quiz/assignments/${aid}/share-links`, { signal }),
    ]);
    if (signal?.aborted || activeSelection.current !== aid) return;
    setSubmissions(s.submissions); setStats(t); setAnalysis(a.analysis); setLinks(l.links);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void refreshList(controller.signal).catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [refreshList]);

  useEffect(() => {
    activeSelection.current = selected; setSubmissions([]); setStats(null); setAnalysis(null); setLinks([]); setDetail(null);
    if (!selected) return;
    const controller = new AbortController();
    let running = false;
    const refresh = async () => {
      if (running) return; running = true;
      try { await Promise.all([refreshDetail(selected, controller.signal), refreshList(controller.signal)]); if (!controller.signal.aborted) setError(''); }
      catch (e) { if (!controller.signal.aborted) setError((e as Error).message); }
      finally { running = false; }
    };
    void refresh(); const timer = setInterval(() => { void refresh(); }, 5000);
    return () => { controller.abort(); clearInterval(timer); };
  }, [selected, refreshDetail, refreshList]);

  useEffect(() => {
    setQr(''); setQrError('');
    if (!share) return;
    const controller = new AbortController(); let url = '';
    void api.blob(`/quiz/assignments/${share.assignment_id}/qr/${share.token}`, { signal: controller.signal }).then(blob => {
      if (controller.signal.aborted) return; url = URL.createObjectURL(blob); setQr(url);
    }).catch(e => { if (!controller.signal.aborted) setQrError(e.message); });
    return () => { controller.abort(); if (url) URL.revokeObjectURL(url); };
  }, [share]);

  async function action(work: () => Promise<void>) {
    setBusy(true); setError('');
    try { await work(); await refreshList(); if (selected) await refreshDetail(selected); }
    catch (e) { setError((e as Error).message); notify((e as Error).message, 'error'); }
    finally { setBusy(false); }
  }

  async function showSubmission(id: string) {
    await action(async () => { const value = await api<Attempt>(`/quiz/submissions/${id}`); if (value.assignment_id === activeSelection.current) { setDetail(value); setReason(''); } });
  }

  async function downloadQr() {
    if (!qr || !share) return;
    await action(async () => {
      const image = new Image(); image.src = qr; await image.decode();
      const canvas = document.createElement('canvas'); canvas.width = 960; canvas.height = 1150;
      const ctx = canvas.getContext('2d'); if (!ctx) throw new Error('浏览器无法生成图片');
      ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, canvas.width, canvas.height); ctx.fillStyle = '#25221e'; ctx.textAlign = 'center'; ctx.font = 'bold 32px sans-serif';
      const a = assignments.find(item => item.id === share.assignment_id);
      ctx.fillText(a?.class_name || className, 480, 65, 880); ctx.font = '26px sans-serif'; ctx.fillText(a?.name || title, 480, 115, 880);
      ctx.drawImage(image, 80, 150, 800, 800); ctx.font = '26px sans-serif'; ctx.fillText('扫码填写姓名，直接开始答题', 480, 1020);
      const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, 'image/png')); if (!blob) throw new Error('二维码图片生成失败');
      download(blob, '班级练习二维码.png');
    });
  }

  const report = analysis?.result ? { result: analysis.result, snapshot: analysis.snapshot, created_at: analysis.created_at, stale: analysis.stale, added_count: analysis.added_count, voided_count: analysis.voided_count } : analysis?.previous;
  const filtered = submissions.filter(s => s.display_name.includes(query)).slice().sort((a, b) => order === 'earliest' ? a.submitted_at.localeCompare(b.submitted_at) : b.submitted_at.localeCompare(a.submitted_at));

  const versions = [...new Set([...assignments].sort((a, b) => a.created_at.localeCompare(b.created_at)).map(a => a.quiz_version_id))];
  function exportReport() {
    if (!report) return;
    const text = `# 班级练习分析\n\n练习：${assignment?.name}\n\n班级：${assignment?.class_name}\n\n生成时间：${date(report.created_at)}\n\n样本：${report.snapshot.attempt_ids.length} 份；${report.stale ? '数据已变更，请更新分析' : '以该报告快照为准'}\n\n${report.result.overview}\n\n${report.result.items.map(i => `## ${i.kind}\n\n${i.text}\n\n关联题目：${i.question_ids.join('、')}`).join('\n\n')}\n\n## 统计依据\n\n${report.snapshot.statistics.questions.map(q => `${q.id} ${q.prompt}：正确 ${q.correct}/${q.total}，正确率 ${percent(q.correct_rate)}`).join('\n\n')}`;
    download(new Blob([text], { type: 'text/markdown;charset=utf-8' }), '班级学情分析.md');
  }

  return <section className="classroom-manager cq-workspace" aria-label="班级练习管理">
    <WorkspaceHeading title={tab === 'submissions' ? '班级答卷' : '学情分析'} meta={`${assignments.length} 次练习`}>
      {tab === 'submissions' && <Button variant="primary" type="button" className="cq-button cq-button-primary" disabled={busy} onClick={() => { setTitle(quizTitle); setClassId(assignment?.class_id || classes[0]?.id || ''); setNewRound(false); setCreateOpen(true); }}>分享给班级</Button>}
    </WorkspaceHeading>
    {error && <InlineFeedback  className="cq-inline-feedback">{error} <Button variant="unstyled" type="button" disabled={busy} onClick={() => void action(async () => {})}>重试</Button></InlineFeedback>}
    {!ready && !error && <LoadingState withSpinner className="cq-dashboard-loading">正在读取班级练习</LoadingState>}
    {ready && !assignments.length && <EmptyState className="cq-empty-workspace"><span aria-hidden="true">▦</span><h3>{tab === 'submissions' ? '还没有发放班级练习' : '暂无可分析的班级练习'}</h3><p>{tab === 'submissions' ? '发放后，学生答卷会显示在这里' : '请先在班级答卷中发放练习并收集答卷'}</p></EmptyState>}
    {!!assignments.length && <>
      <div className="cq-context-bar"><AssignmentPicker assignments={assignments} selected={selected} onChange={setSelected} disabled={busy} />
        <div className="cq-context-copy"><strong title={assignment?.name}>{assignment?.name}</strong><span>题目版本 V{versions.indexOf(assignment?.quiz_version_id || '') + 1} · {assignment && assignmentTime(assignment.created_at)}</span></div>
        <span className={`cq-status ${assignment?.status === 'OPEN' ? 'is-open' : ''}`}><i />{assignment?.status === 'OPEN' ? '开放中' : '已关闭'}</span>
        {tab === 'submissions' && <div className="cq-actions"><Button variant="outline" type="button" className="cq-button" disabled={busy} onClick={() => void action(async () => { setShare(await api<ShareLink>(`/quiz/assignments/${selected}/share-links`, { method: 'POST' })); })}>分享二维码</Button>
          <Button variant="ghost" type="button" className="cq-button cq-button-quiet" disabled={busy} onClick={() => void action(async () => {
            if (assignment?.status === 'OPEN' && !await confirm('关闭后，未提交的学生将暂时无法交卷；重新开放后可继续。')) return;
            await api(`/quiz/assignments/${selected}`, { method: 'PATCH', body: JSON.stringify({ status: assignment?.status === 'OPEN' ? 'CLOSED' : 'OPEN' }) });
          })}>{assignment?.status === 'OPEN' ? '关闭练习' : '重新开放'}</Button></div>}
      </div>
      {!view && <nav className="classroom-tabs cq-view-tabs" aria-label="班级练习视图"><Button variant="unstyled" type="button" aria-pressed={tab === 'submissions'} onClick={() => setTab('submissions')}>班级答卷</Button><Button variant="unstyled" type="button" aria-pressed={tab === 'analysis'} onClick={() => setTab('analysis')}>学情分析</Button></nav>}
      {tab === 'submissions' ? <div className="cq-collection">
        <section className="cq-panel cq-submissions-panel"><header className="cq-collection-toolbar"><div className="cq-collection-title"><h3>已提交答卷</h3><span>{stats?.submitted_count ?? assignment?.submitted_count ?? 0}</span></div>
          <div className="cq-collection-tools"><label className="cq-search"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4.5 4.5" /></svg><span className="sr-only">搜索学生</span><input placeholder="搜索姓名" value={query} onChange={e => setQuery(e.target.value)} /></label>
            <label className="cq-sort"><span className="sr-only">提交顺序</span><FormSelect ariaLabel="提交顺序" value={order} onValueChange={setOrder} options={[{ value: "latest", label: "最新提交" }, { value: "earliest", label: "最早提交" }]} /></label>
            <Button variant="outline" type="button" className="cq-button" disabled={busy || !submissions.length} onClick={() => void action(async () => { download(await api.blob(`/quiz/assignments/${selected}/export`), '班级答题明细.csv'); })}>↓ 导出明细</Button></div>
        </header><SubmissionTable rows={filtered} busy={busy} onView={id => void showSubmission(id)} filtered={Boolean(query)} />
          <footer className="cq-table-footer"><span>共 {submissions.length} 份有效答卷{query ? ` · 筛选出 ${filtered.length} 份` : ''}</span><span><i />自动更新</span></footer>
        </section>
        <details className="cq-share-management"><summary>分享链接管理<span>{links.filter(l => !l.revoked_at).length} 个有效入口</span></summary><div>{links.map(l => <div className="cq-share-row" key={l.id}><span>{date(l.created_at)}</span><span className={l.revoked_at ? '' : 'cq-share-active'}>{l.revoked_at ? '已撤销' : '有效'}</span>{!l.revoked_at && <Button variant="ghost" type="button" className="cq-button cq-button-quiet" disabled={busy} onClick={() => void action(async () => { if (await confirm('撤销后，该链接不能再供新学生进入。')) await api(`/quiz/assignments/${selected}/share-links/${l.id}`, { method: 'DELETE' }); })}>撤销入口</Button>}</div>)}</div></details>
      </div> : <LearningDashboard key={selected} stats={stats} analysis={analysis} report={report} busy={busy} onAnalyze={() => void action(async () => { await api(`/quiz/assignments/${selected}/analyses`, { method: 'POST' }); })} onExport={exportReport} onStudent={id => void showSubmission(id)} />}
    </>}

    <Dialog.Root open={createOpen} onOpenChange={value => { if (!busy) setCreateOpen(value); }}><Dialog.Surface className="asset-confirm-dialog radix-confirm-content classroom-dialog cq-config-dialog" aria-describedby={undefined}><Dialog.Title>分享给班级</Dialog.Title><form onSubmit={e => { e.preventDefault(); void action(async () => {
      const value = await api<ShareLink>(`/jobs/${jobId}/quiz/assignments`, { method: 'POST', body: JSON.stringify({ class_id: classId || null, class_name: className, name: title, new_round: newRound }) });
      setCreateOpen(false); setSelected(value.assignment_id); setShare(value); if (value.reused) notify('已打开已有班级练习，答卷继续保留', 'success');
    }); }}><label>班级<FormSelect ariaLabel="班级" value={classId} onValueChange={setClassId} disabled={busy} options={[{ value: "", label: "新建班级" }, ...classes.map(c => ({ value: c.id, label: c.name }))]} /></label>{!classId && <label>班级名称<input required maxLength={100} value={className} onChange={e => setClassName(e.target.value)} placeholder="例如：三年级二班" /></label>}<label>练习名称<input required maxLength={120} value={title} onChange={e => setTitle(e.target.value)} /></label>{error && <InlineFeedback  >{error}</InlineFeedback>}<label className="cq-new-round"><input type="checkbox" checked={newRound} onChange={e => setNewRound(e.target.checked)} /><span>新建一轮练习<small>单独收卷，已有学生可再次参加</small></span></label><div className="classroom-toolbar"><Button variant="primary" type="submit" disabled={busy}>{busy ? '正在创建…' : '生成分享二维码'}</Button><Button variant="outline" type="button" disabled={busy} onClick={() => setCreateOpen(false)}>取消</Button></div></form></Dialog.Surface></Dialog.Root>

    <Dialog.Root open={!!share} onOpenChange={value => { if (!value) setShare(null); }}><Dialog.Surface className="asset-confirm-dialog radix-confirm-content classroom-dialog classroom-share" aria-describedby={undefined}><div ref={shareRef} className="classroom-share-content"><Dialog.Title>扫码开始班级练习</Dialog.Title><p>{assignments.find(a => a.id === share?.assignment_id)?.class_name || className} · {assignments.find(a => a.id === share?.assignment_id)?.name || title}</p>{qr ? <img src={qr} alt="班级练习分享二维码" width={300} height={300} /> : <p>{qrError || '正在生成二维码…'}</p>}<p>学生只需填写姓名，提交后查看答案。</p><div className="classroom-toolbar"><Button variant="unstyled" type="button" disabled={!share} onClick={() => void action(async () => { await navigator.clipboard.writeText(share!.url); notify('链接已复制', 'success'); })}>复制链接</Button><Button variant="unstyled" type="button" disabled={!qr || busy} onClick={() => void downloadQr()}>下载二维码</Button><Button variant="unstyled" type="button" onClick={() => void action(async () => { if (document.fullscreenElement) await document.exitFullscreen(); else await shareRef.current?.requestFullscreen(); })}>全屏投屏</Button><Button variant="unstyled" type="button" onClick={() => { if (document.fullscreenElement) void document.exitFullscreen(); setShare(null); }}>关闭</Button></div>{share && <input aria-label="分享链接" readOnly value={share.url} onFocus={e => e.target.select()} />}</div></Dialog.Surface></Dialog.Root>

    <Dialog.Root open={!!detail} onOpenChange={value => { if (!value && !busy) setDetail(null); }}>
      <Dialog.Surface className="asset-confirm-dialog radix-confirm-content classroom-answer-dialog" aria-labelledby="classroom-answer-title" aria-describedby={undefined}>
        <DialogHeader className="classroom-answer-heading" title={`${detail?.display_name ?? ''}的答卷`} subtitle={detail && <>{detail.assignment_name} · {detail.submitted_at && date(detail.submitted_at)}</>} busy={busy} titleId="classroom-answer-title" onClose={() => setDetail(null)} />
        {detail && <div className="classroom-answer-scroll">
          <AnswerCardGrid attempt={detail} />
          <details className="classroom-answer-administration"><summary>答卷管理</summary><label>作废原因<input maxLength={400} value={reason} onChange={e => setReason(e.target.value)} placeholder="误填、同名或其他原因" /></label>
            <Button variant="unstyled" type="button" disabled={busy || !reason.trim()} onClick={() => void action(async () => { if (!await confirm('作废后，本答卷退出统计，原姓名可以重新开始。')) return; await api(`/quiz/submissions/${detail.id}/void`, { method: 'POST', body: JSON.stringify({ reason }) }); setDetail(null); })}>作废答卷</Button>
          </details>
        </div>}
        {error && <InlineFeedback  className="classroom-answer-error">{error}</InlineFeedback>}
      </Dialog.Surface>
    </Dialog.Root>
  </section>;
}

