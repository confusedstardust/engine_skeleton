'use client';
import { LoadingState } from './ui/state';
import { InlineFeedback } from './ui/feedback';
import { EmptyState } from './ui/state';

import { DialogHeader } from './ui/dialog-header';

import { FormSelect } from './ui/form-controls';
import { Button } from './ui/button';
import './classroom-quiz.css';

import { useEffect, useRef, useState } from 'react';
import { useRefreshPolling } from '../hooks/use-refresh-polling';
import { useLazyResource } from '../hooks/use-lazy-resource';
import { submissionKey } from '../domain/submission-changes';
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

export function ClassroomQuizManager({ jobId, quizTitle, view, active = true }: { jobId: string; quizTitle: string; view?: 'submissions' | 'analysis'; active?: boolean }) {
  const [tab, setTab] = useState<'submissions' | 'analysis'>('submissions');
  const [selected, setSelected] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [classId, setClassId] = useState('');
  const [className, setClassName] = useState('');
  const [title, setTitle] = useState(quizTitle);
  const [share, setShare] = useState<ShareLink | null>(null);
  const [qr, setQr] = useState('');
  const [qrError, setQrError] = useState('');
  const [linksOpen, setLinksOpen] = useState(false);
  const [submissionsLoaded, setSubmissionsLoaded] = useState('');
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [detail, setDetail] = useState<Attempt | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const detailRequest = useRef<AbortController | null>(null);
  const detailTarget = useRef('');
  const detailCache = useRef(new Map<string, Attempt>());
  const [reason, setReason] = useState('');
  const [query, setQuery] = useState('');
  const [order, setOrder] = useState('latest');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const shareRef = useRef<HTMLDivElement>(null);
  const activeSelection = useRef('');
  const notify = useToast(); const confirm = useConfirmation();
  activeSelection.current = selected;
  useEffect(() => { if (view) setTab(view); }, [view]);

  const currentTab = view || tab;
  const list = useLazyResource(`assignments:${jobId}`, signal => api<{ assignments: Assignment[] }>(`/jobs/${jobId}/quiz/assignments`, { signal }), active);
  const groups = useLazyResource(`classes:${jobId}`, signal => api<{ classes: { id: string; name: string }[] }>('/quiz/classes', { signal }), createOpen);
  const linkList = useLazyResource(`links:${selected}`, signal => api<{ links: { id: string; created_at: string; revoked_at: string | null }[] }>(`/quiz/assignments/${selected}/share-links`, { signal }), active && currentTab === 'submissions' && linksOpen && !!selected);
  const statistics = useLazyResource(`statistics:${selected}`, signal => api<QuizStatistics>(`/quiz/assignments/${selected}/statistics`, { signal }), active && currentTab === 'analysis' && !!selected && submissionsLoaded === selected && !detailOpen);
  const latest = useLazyResource(`latest:${selected}`, signal => api<{ analysis: Analysis | null }>(`/quiz/assignments/${selected}/analyses/latest`, { signal }), active && currentTab === 'analysis' && !!selected && !detailOpen);
  const assignments = list.data?.assignments || [];
  const classes = groups.data?.classes || [];
  const links = linkList.data?.links || [];
  const stats = statistics.data || null;
  const analysis = latest.data?.analysis || null;
  const ready = list.loaded;
  const assignment = assignments.find(a => a.id === selected);
  const previousSubmissions = useRef(new Map<string, string>());

  useEffect(() => {
    if (!list.loaded) return;
    setSelected(value => assignments.some(a => a.id === value) ? value : assignments.find(a => a.submitted_count > 0)?.id || assignments[0]?.id || '');
  }, [list.data, list.loaded]);

  const sync = useRefreshPolling(async signal => {
    const aid = selected;
    const value = await api<{ submissions: Submission[] }>(`/quiz/assignments/${aid}/submissions`, { signal });
    const key = submissionKey(value.submissions);
    return {
      key, closed: assignment?.status === 'CLOSED', poll: assignment?.status === 'OPEN',
      commit: () => {
        if (signal.aborted || activeSelection.current !== aid) return;
        const previous = previousSubmissions.current.get(aid);
        if (previous !== undefined && previous !== key) statistics.invalidate();
        previousSubmissions.current.set(aid, key);
        const rows = new Map(value.submissions.map(row => [row.id, row]));
        for (const [id, cached] of detailCache.current) {
          const row = rows.get(id);
          if (cached.assignment_id === aid && (!row || row.display_name !== cached.display_name || row.submitted_at !== cached.submitted_at)) detailCache.current.delete(id);
        }
        setSubmissions(value.submissions); setSubmissionsLoaded(aid);
        list.update(data => ({ assignments: (data?.assignments || []).map(a => a.id === aid ? { ...a, submitted_count: value.submissions.length } : a) }));
      },
    };
  }, { resetKey: `${jobId}:${selected}:${assignment?.status}`, enabled: active && !!selected, suspended: detailOpen });

  useEffect(() => {
    setSubmissions([]); setSubmissionsLoaded(''); setLinksOpen(false);
    setDetail(null); setDetailOpen(false); setDetailError(''); setDetailLoading(false);
    detailRequest.current?.abort();
    return () => detailRequest.current?.abort();
  }, [selected]);

  useEffect(() => {
    const clear = () => { detailCache.current.clear(); closeDetail(); };
    window.addEventListener('forge-auth-changed', clear);
    return () => window.removeEventListener('forge-auth-changed', clear);
  }, []);

  const resourceError = list.error || (createOpen ? groups.error : '') || (linksOpen ? linkList.error : '') || (currentTab === 'analysis' ? statistics.error || latest.error : '') || sync.error;
  async function retryResources() {
    if (list.error) await list.load(true);
    if (groups.error && createOpen) await groups.load(true);
    if (linkList.error && linksOpen) await linkList.load(true);
    if (currentTab === 'analysis') {
      if (statistics.error) await statistics.load(true);
      if (latest.error) await latest.load(true);
    }
    if (sync.error) await sync.refresh();
  }

  useEffect(() => {
    setQr(''); setQrError('');
    if (!share) return;
    const controller = new AbortController(); let url = '';
    void api.blob(`/quiz/assignments/${share.assignment_id}/qr/${share.token}`, { signal: controller.signal }).then(blob => {
      if (controller.signal.aborted) return; url = URL.createObjectURL(blob); setQr(url);
    }).catch(e => { if (!controller.signal.aborted) setQrError(e.message); });
    return () => { controller.abort(); if (url) URL.revokeObjectURL(url); };
  }, [share]);

  async function action(work: () => Promise<void>, options: { inlineError?: boolean } = {}) {
    setBusy(true); setError('');
    try {
      await work();

    } catch (e) {
      if ((e as Error).name !== 'AbortError' && !options.inlineError) { setError((e as Error).message); notify((e as Error).message, 'error'); }
    } finally { setBusy(false); }
  }

  function closeDetail() {
    detailRequest.current?.abort(); setDetailOpen(false); setDetail(null); setDetailLoading(false); setDetailError('');
  }

  async function showSubmission(id: string) {
    detailRequest.current?.abort();
    detailTarget.current = id;
    const cached = detailCache.current.get(id);
    if (cached && cached.assignment_id === selected) {
      setDetail({ ...cached, assignment_name: assignment?.name || cached.assignment_name, assignment_status: assignment?.status || cached.assignment_status });
      setDetailError(''); setDetailOpen(true); setDetailLoading(false); setReason('');
      return;
    }
    const controller = new AbortController(); detailRequest.current = controller;
    const aid = selected;
    detailTarget.current = id;
    setDetail(null); setDetailError(''); setDetailOpen(true); setDetailLoading(true);
    await action(async () => {
      try {
        const value = await api<Attempt>(`/quiz/submissions/${id}`, { signal: controller.signal });
        if (!controller.signal.aborted && value.assignment_id === activeSelection.current && aid === activeSelection.current) {
          if (value.status === 'SUBMITTED') detailCache.current.set(id, value);
          setDetail(value); setReason('');
        }
      } catch (e) {
        if (!controller.signal.aborted) setDetailError((e as Error).message);
        throw e;
      } finally { if (detailRequest.current === controller) setDetailLoading(false); }
    }, { inlineError: true });
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

  const savedReport = analysis?.result ? { result: analysis.result, snapshot: analysis.snapshot, created_at: analysis.created_at, stale: analysis.stale, added_count: analysis.added_count, voided_count: analysis.voided_count } : analysis?.previous;
  const sample = new Set(savedReport?.snapshot.attempt_ids || []);
  const currentIds = new Set(submissions.map(s => s.id));
  const added = [...currentIds].filter(id => !sample.has(id)).length;
  const voided = [...sample].filter(id => !currentIds.has(id)).length;
  const report = savedReport ? { ...savedReport, stale: savedReport.stale || added > 0 || voided > 0, added_count: added, voided_count: voided } : null;
  const filtered = submissions.filter(s => s.display_name.includes(query)).slice().sort((a, b) => order === 'earliest' ? a.submitted_at.localeCompare(b.submitted_at) : b.submitted_at.localeCompare(a.submitted_at));

  const versions = [...new Set([...assignments].sort((a, b) => a.created_at.localeCompare(b.created_at)).map(a => a.quiz_version_id))];
  function exportReport() {
    if (!report) return;
    const text = `# 班级练习分析\n\n练习：${assignment?.name}\n\n班级：${assignment?.class_name}\n\n生成时间：${date(report.created_at)}\n\n样本：${report.snapshot.attempt_ids.length} 份；${report.stale ? '数据已变更，请更新分析' : '以该报告快照为准'}\n\n${report.result.overview}\n\n${report.result.items.map(i => `## ${i.kind}\n\n${i.text}\n\n关联题目：${i.question_ids.join('、')}`).join('\n\n')}\n\n## 统计依据\n\n${report.snapshot.statistics.questions.map(q => `${q.id} ${q.prompt}：正确 ${q.correct}/${q.total}，正确率 ${percent(q.correct_rate)}`).join('\n\n')}`;
    download(new Blob([text], { type: 'text/markdown;charset=utf-8' }), '班级学情分析.md');
  }

  return <section className="classroom-manager cq-workspace" aria-label="班级练习管理">
    <WorkspaceHeading title={currentTab === 'submissions' ? '班级答卷' : '学情分析'} meta={`${assignments.length} 次练习`}>
      {currentTab === 'submissions' && <Button size="sm" variant="primary" type="button" className="cq-button" disabled={busy} onClick={() => { setTitle(quizTitle); setClassId(assignment?.class_id || classes[0]?.id || ''); setCreateOpen(true); }}>分享给班级</Button>}
    </WorkspaceHeading>
    {(error || resourceError) && <InlineFeedback className="cq-inline-feedback">{error || resourceError} <Button variant="unstyled" type="button" disabled={busy} onClick={() => { setError(''); void retryResources(); }}>重试</Button></InlineFeedback>}
    {!ready && !error && !resourceError && <LoadingState withSpinner className="cq-dashboard-loading">正在读取班级练习</LoadingState>}
    {ready && !assignments.length && <EmptyState className="cq-empty-workspace"><span aria-hidden="true">▦</span><h3>{currentTab === 'submissions' ? '还没有发放班级练习' : '暂无可分析的班级练习'}</h3><p>{currentTab === 'submissions' ? '发放后，学生答卷会显示在这里' : '请先在班级答卷中发放练习并收集答卷'}</p></EmptyState>}
    {!!assignments.length && <>
      <div className="cq-context-bar"><AssignmentPicker assignments={assignments} selected={selected} onChange={setSelected} disabled={busy} />
        <div className="cq-context-copy"><strong title={assignment?.name}>{assignment?.name}</strong><span>题目版本 V{versions.indexOf(assignment?.quiz_version_id || '') + 1} · {assignment && assignmentTime(assignment.created_at)}</span></div>
        <span className={`cq-status ${assignment?.status === 'OPEN' ? 'is-open' : ''}`}><i />{assignment?.status === 'OPEN' ? '开放中' : '已关闭'}</span>
        {currentTab === 'submissions' && <div className="cq-actions"><Button size="sm" variant="outline" type="button" className="cq-button" disabled={busy} onClick={() => void action(async () => { setShare(await api<ShareLink>(`/quiz/assignments/${selected}/share-links`, { method: 'POST' })); linkList.invalidate(); })}>分享二维码</Button>
          <Button size="sm" variant="ghost" type="button" className="cq-button" disabled={busy} onClick={() => void action(async () => {
            if (assignment?.status === 'OPEN' && !await confirm('关闭后，未提交的学生将暂时无法交卷；重新开放后可继续。')) return;
            await api(`/quiz/assignments/${selected}`, { method: 'PATCH', body: JSON.stringify({ status: assignment?.status === 'OPEN' ? 'CLOSED' : 'OPEN' }) }); await list.load(true);
          })}>{assignment?.status === 'OPEN' ? '关闭练习' : '重新开放'}</Button></div>}
      </div>
      {!view && <nav className="classroom-tabs cq-view-tabs" aria-label="班级练习视图"><Button variant="unstyled" type="button" aria-pressed={currentTab === 'submissions'} onClick={() => setTab('submissions')}>班级答卷</Button><Button variant="unstyled" type="button" aria-pressed={currentTab === 'analysis'} onClick={() => setTab('analysis')}>学情分析</Button></nav>}
      {currentTab === 'submissions' ? <div className="cq-collection">
        <section className="cq-panel cq-submissions-panel"><header className="cq-collection-toolbar"><div className="cq-collection-title"><h3>已提交答卷</h3><span>{submissionsLoaded === selected ? submissions.length : assignment?.submitted_count ?? 0}</span></div>
          <div className="cq-collection-tools"><label className="cq-search"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4.5 4.5" /></svg><span className="sr-only">搜索学生</span><input placeholder="搜索姓名" value={query} onChange={e => setQuery(e.target.value)} /></label>
            <label className="cq-sort"><span className="sr-only">提交顺序</span><FormSelect ariaLabel="提交顺序" value={order} onValueChange={setOrder} options={[{ value: "latest", label: "最新提交" }, { value: "earliest", label: "最早提交" }]} /></label>
            <Button size="sm" variant="outline" type="button" className="cq-button" disabled={busy || !submissions.length} onClick={() => void action(async () => { download(await api.blob(`/quiz/assignments/${selected}/export`), '班级答题明细.csv'); })}>↓ 导出明细</Button></div>
        </header><SubmissionTable rows={filtered} busy={busy} onView={id => void showSubmission(id)} filtered={Boolean(query)} />
          <footer className="cq-table-footer"><span>共 {submissions.length} 份有效答卷{query ? ` · 筛选出 ${filtered.length} 份` : ''}</span><span role="status"><i />{sync.error ? '同步失败' : sync.syncing ? '同步中…' : sync.paused ? '已暂停自动更新' : `自动更新 · ${Math.round(sync.delayMs / 1000)} 秒`}</span></footer>
        </section>
        <details className="cq-share-management" open={linksOpen} onToggle={event => setLinksOpen(event.currentTarget.open)}><summary>分享链接管理{linkList.loaded && !linkList.dirty && <span>{links.filter(l => !l.revoked_at).length} 个有效入口</span>}</summary>{linkList.loading && <LoadingState inline>正在读取分享入口…</LoadingState>}<div>{links.map(l => <div className="cq-share-row" key={l.id}><span>{date(l.created_at)}</span><span className={l.revoked_at ? '' : 'cq-share-active'}>{l.revoked_at ? '已撤销' : '有效'}</span>{!l.revoked_at && <Button size="sm" variant="ghost" type="button" className="cq-button" disabled={busy} onClick={() => void action(async () => { if (await confirm('撤销后，该链接不能再供新学生进入。')) { await api(`/quiz/assignments/${selected}/share-links/${l.id}`, { method: 'DELETE' }); linkList.invalidate(); } })}>撤销入口</Button>}</div>)}</div></details>
      </div> : <LearningDashboard key={selected} stats={stats} analysis={analysis} report={report} busy={busy} onAnalyze={() => void action(async () => { await api(`/quiz/assignments/${selected}/analyses`, { method: 'POST' }); await latest.load(true); })} onRefresh={() => void latest.load(true)} refreshing={latest.loading} onExport={exportReport} onStudent={id => void showSubmission(id)} />}
    </>}

    <Dialog.Root busy={busy} open={createOpen} onOpenChange={value => { if (!busy) setCreateOpen(value); }}><Dialog.Surface className="asset-confirm-dialog radix-confirm-content classroom-dialog cq-config-dialog" aria-describedby={undefined}><DialogHeader dialogTitle title="分享给班级" busy={busy} onClose={() => setCreateOpen(false)} /><form onSubmit={e => { e.preventDefault(); void action(async () => {
      const value = await api<ShareLink>(`/jobs/${jobId}/quiz/assignments`, { method: 'POST', body: JSON.stringify({ class_id: classId || null, class_name: className, name: title }) });
      await list.load(true); if (!classId) await groups.load(true); setCreateOpen(false); setSelected(value.assignment_id); setShare(value); if (value.reused) notify('已打开已有班级练习，答卷继续保留', 'success');
    }); }}><label>班级<FormSelect ariaLabel="班级" value={classId} onValueChange={setClassId} disabled={busy} options={[{ value: "", label: "新建班级" }, ...classes.map(c => ({ value: c.id, label: c.name }))]} /></label>{groups.loading && <LoadingState inline>正在读取班级…</LoadingState>}{!classId && <label>班级名称<input required maxLength={100} value={className} onChange={e => setClassName(e.target.value)} placeholder="例如：三年级二班" /></label>}<label>练习名称<input required maxLength={120} value={title} onChange={e => setTitle(e.target.value)} /></label>{error && <InlineFeedback  >{error}</InlineFeedback>}<div className="classroom-toolbar"><Button variant="primary" type="submit" disabled={busy}>{busy ? '正在创建…' : '生成分享二维码'}</Button><Button variant="outline" type="button" disabled={busy} onClick={() => setCreateOpen(false)}>取消</Button></div></form></Dialog.Surface></Dialog.Root>

    <Dialog.Root open={!!share} onOpenChange={value => { if (!value) setShare(null); }}><Dialog.Surface className="asset-confirm-dialog radix-confirm-content classroom-dialog classroom-share" aria-describedby={undefined}><div ref={shareRef} className="classroom-share-content"><Dialog.Title>扫码开始班级练习</Dialog.Title><p>{assignments.find(a => a.id === share?.assignment_id)?.class_name || className} · {assignments.find(a => a.id === share?.assignment_id)?.name || title}</p>{qr ? <img src={qr} alt="班级练习分享二维码" width={300} height={300} /> : qrError ? <InlineFeedback>{qrError}</InlineFeedback> : <LoadingState withSpinner className="classroom-qr-loading">正在生成二维码…</LoadingState>}<div className="classroom-toolbar"><Button variant="unstyled" type="button" disabled={!share} onClick={() => void action(async () => { await navigator.clipboard.writeText(share!.url); notify('链接已复制', 'success'); })}>复制链接</Button><Button variant="unstyled" type="button" disabled={!qr || busy} onClick={() => void downloadQr()}>下载二维码</Button><Button variant="unstyled" type="button" onClick={() => void action(async () => { if (document.fullscreenElement) await document.exitFullscreen(); else await shareRef.current?.requestFullscreen(); })}>全屏投屏</Button><Button variant="unstyled" type="button" onClick={() => { if (document.fullscreenElement) void document.exitFullscreen(); setShare(null); }}>关闭</Button></div>{share && <input aria-label="分享链接" readOnly value={share.url} onFocus={e => e.target.select()} />}</div></Dialog.Surface></Dialog.Root>

    <Dialog.Root busy={busy && !detailLoading} open={detailOpen} onOpenChange={value => { if (!value) closeDetail(); }}>
      <Dialog.Surface className="asset-confirm-dialog radix-confirm-content classroom-answer-dialog" aria-labelledby="classroom-answer-title" aria-describedby={undefined}>
        <DialogHeader dialogTitle className="classroom-answer-heading" title={detail ? `${detail.display_name}的答卷` : '查看答卷'} subtitle={detail && <>{detail.assignment_name} · {detail.submitted_at && date(detail.submitted_at)}</>} busy={busy && !detailLoading} titleId="classroom-answer-title" onClose={closeDetail} />
        {detailLoading && <LoadingState>正在读取答卷…</LoadingState>}
        {detailError && <InlineFeedback className="classroom-answer-error">{detailError} <Button disabled={busy} onClick={() => void showSubmission(detailTarget.current)}>重试</Button></InlineFeedback>}
        {detail && <div className="classroom-answer-scroll">
          <AnswerCardGrid attempt={detail} />
          <details className="classroom-answer-administration"><summary>答卷管理</summary><label>作废原因<input maxLength={400} value={reason} onChange={e => setReason(e.target.value)} placeholder="误填、同名或其他原因" /></label>
            <Button variant="unstyled" type="button" disabled={busy || !reason.trim()} onClick={() => void action(async () => { if (!await confirm('作废后，本答卷退出统计，原姓名可以重新开始。')) return; await api(`/quiz/submissions/${detail.id}/void`, { method: 'POST', body: JSON.stringify({ reason }) }); detailCache.current.delete(detail.id); closeDetail(); await sync.refresh({ mutation: true }); })}>作废答卷</Button>
          </details>
        </div>}
        {error && <InlineFeedback  className="classroom-answer-error">{error}</InlineFeedback>}
      </Dialog.Surface>
    </Dialog.Root>
  </section>;
}

