'use client';
import { InlineFeedback } from '../../../../components/ui/feedback';

import { Button } from '../../../../components/ui/button';

import { use, useCallback, useEffect, useRef, useState } from 'react';
import { createApiClient, ApiError } from '../../../../lib/api-client';
import type { Attempt, StudentSession } from '../../../../domain/classroom-quiz';
import * as Dialog from '../../../../components/ui/dialog';
import { useConfirmation } from '../../../../components/ui/modal';

const api = createApiClient('/api/forge', { inviteAuth: false });
type Saved = { session: StudentSession; answers: Record<string, string> };

export default function StudentPractice({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  return <StudentWorkspace key={token} token={token} />;
}

function StudentWorkspace({ token }: { token: string }) {
  const storageKey = `classroom-quiz:${token}`;
  const [session, setSession] = useState<StudentSession | null>(null);
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [info, setInfo] = useState<{ name: string; status: string } | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [name, setName] = useState('');
  const [editing, setEditing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [storageWarning, setStorageWarning] = useState('');
  const [invalidSession, setInvalidSession] = useState(false);
  const current = useRef<StudentSession | null>(null);
  const confirm = useConfirmation();
  const fetchAttempt = useCallback((s: StudentSession, signal?: AbortSignal) => api<Attempt>(`/public/quiz/attempts/${s.id}`, { signal, headers: { 'X-Quiz-Credential': s.credential } }), []);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        let saved: Saved | null = null;
        try { saved = JSON.parse(localStorage.getItem(storageKey) || 'null') as Saved | null; }
        catch { setStorageWarning('浏览器暂不能保存进度，请保持本页打开直至提交成功。'); }
        if (saved?.session?.id && saved.session.credential) {
          try {
            const value = await fetchAttempt(saved.session, controller.signal);
            if (controller.signal.aborted) return;
            current.current = saved.session; setSession(saved.session); setAttempt(value); setName(value.display_name);
            setAnswers(value.status === 'SUBMITTED' ? {} : saved.answers || {});
            return;
          } catch (reason) {
            if (controller.signal.aborted) return;
            if (reason instanceof ApiError && [401, 404, 410].includes(reason.status)) setInvalidSession(true);
            throw reason;
          }
        }
        const value = await api<{ name: string; status: string }>(`/public/quiz/${token}`, { signal: controller.signal });
        if (!controller.signal.aborted) setInfo(value);
      } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : '习题暂时无法加载'); }
      finally { if (!controller.signal.aborted) setLoading(false); }
    }
    void load();
    return () => controller.abort();
  }, [fetchAttempt, storageKey, token]);

  useEffect(() => {
    if (!session || !attempt) return;
    try { localStorage.setItem(storageKey, JSON.stringify({ session, answers: attempt.status === 'DRAFT' ? answers : {} })); }
    catch { setStorageWarning('浏览器暂不能保存进度，请保持本页打开直至提交成功。'); }
  }, [session, answers, attempt?.status, storageKey]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!session || attempt?.status !== 'DRAFT') return;
    const controller = new AbortController();
    let active = true;
    const timer = window.setInterval(() => {
      void fetchAttempt(session, controller.signal).then(value => { if (active && current.current?.id === session.id) setAttempt(value); })
        .catch(reason => { if (active) { setError(reason.message); if (reason instanceof ApiError && [401, 404, 410].includes(reason.status)) setInvalidSession(true); } });
    }, 10000);
    return () => { active = false; controller.abort(); window.clearInterval(timer); };
  }, [session, attempt?.status, fetchAttempt]);

  async function begin() {
    if (!name.trim()) return;
    setBusy(true); setError('');
    try {
      if (editing && session) {
        const value = await api<Attempt>(`/public/quiz/attempts/${session.id}/identity`, { method: 'PATCH', headers: { 'X-Quiz-Credential': session.credential }, body: JSON.stringify({ name }) });
        setAttempt(value); setName(value.display_name); setEditing(false);
      } else {
        const value = session || await api<StudentSession>(`/public/quiz/${token}/join`, { method: 'POST', body: JSON.stringify({ name }) });
        // Store the credential immediately, before the follow-up read can fail.
        current.current = value; setSession(value); setAnswers({});
        try { localStorage.setItem(storageKey, JSON.stringify({ session: value, answers: {} })); } catch { setStorageWarning('请保持本页打开直至提交成功。'); }
        const result = await fetchAttempt(value); setAttempt(result); setName(result.display_name);
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : '暂时无法开始作答'); }
    finally { setBusy(false); }
  }

  async function submit() {
    if (!attempt || !session) return;
    const missing = attempt.quiz.questions.find(q => !answers[q.id]);
    if (missing) { setError('请完成全部题目后提交'); document.getElementById(`question-${missing.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }); return; }
    setBusy(true); setError('');
    try {
      const result = await api<Attempt>(`/public/quiz/attempts/${session.id}/submit`, {
        method: 'POST', headers: { 'X-Quiz-Credential': session.credential },
        body: JSON.stringify({ answers: attempt.quiz.questions.map(q => ({ question_id: q.id, option_id: answers[q.id] })) }),
      });
      setAttempt(result); setAnswers({}); window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (reason) { setError(reason instanceof Error ? reason.message : '提交失败，答案已保留，请重试'); }
    finally { setBusy(false); }
  }

  async function clearInvalid() {
    try { localStorage.removeItem(storageKey); } catch { /* Memory reset still works. */ }
    current.current = null; setSession(null); setAttempt(null); setAnswers({}); setName(''); setInvalidSession(false); setError('');
    try { setInfo(await api(`/public/quiz/${token}`)); } catch (reason) { setError((reason as Error).message); }
  }

  async function switchStudent() {
    if (!await confirm(attempt?.status === 'SUBMITTED' ? '将清除本设备的答卷访问记录，供下一位同学填写姓名。原答卷仍然保留，同名不能再次提交；清除后不能仅凭姓名找回答卷。' : '更换作答人会清空本设备当前未提交的答案，并重新填写姓名。')) return;
    setBusy(true);
    try {
      const value = await api<{ name: string; status: string }>(`/public/quiz/${token}`);
      try { localStorage.removeItem(storageKey); } catch { /* Reset memory even if storage is unavailable. */ }
      current.current = null; setSession(null); setAttempt(null); setAnswers({}); setName(''); setEditing(false); setError(''); setInfo(value);
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  }

  const submitted = attempt?.status === 'SUBMITTED';
  const closed = attempt?.assignment_status === 'CLOSED';
  const completed = attempt?.quiz.questions.filter(q => answers[q.id]).length || 0;
  const showName = !loading && !invalidSession && ((Boolean(info) && !attempt && info?.status === 'OPEN') || editing);

  return <main className="practice-page classroom-student">
    <header className="classroom-heading"><span className="practice-kicker">CLASSROOM PRACTICE</span><h1>{attempt?.assignment_name || info?.name || '班级习题'}</h1>
      {attempt && <p>{submitted ? '已提交' : `${attempt.display_name} · 作答中`} {!submitted && !invalidSession && <><Button variant="unstyled" type="button" className="classroom-link" disabled={busy} onClick={() => { setEditing(true); setError(''); }}>修改姓名</Button><Button variant="unstyled" type="button" className="classroom-link" disabled={busy} onClick={() => void switchStudent()}>更换作答人</Button></>}</p>}
    </header>
    {loading && <p role="status">正在读取习题…</p>}
    {storageWarning && <p role="status">{storageWarning}</p>}
    {error && <InlineFeedback  >{error}</InlineFeedback>}
    {invalidSession && <Button type="button" variant="outline" onClick={() => void clearInvalid()}>清除本设备失效记录</Button>}
    {!loading && !attempt && info?.status === 'CLOSED' && <p>练习已关闭，请联系老师。</p>}
    {!loading && error && !attempt && !info && !invalidSession && <Button variant="unstyled" type="button" onClick={() => window.location.reload()}>重新加载</Button>}
    <Dialog.Root open={showName} onOpenChange={open => { if (!open && editing && !busy) setEditing(false); }}>
      <Dialog.Surface className="asset-confirm-dialog radix-confirm-content classroom-name-dialog" aria-describedby={undefined} onEscapeKeyDown={e => { if (!editing || busy) e.preventDefault(); }} onPointerDownOutside={e => e.preventDefault()}>
        <Dialog.Title className="sr-only">{editing ? '修改姓名' : '姓名'}</Dialog.Title>
        <form onSubmit={e => { e.preventDefault(); void begin(); }}><label>姓名<input autoFocus required maxLength={40} autoComplete="name" value={name} disabled={busy} onChange={e => setName(e.target.value)} /></label>
          {error && <InlineFeedback  >{error}</InlineFeedback>}
          <Button type="submit" variant="primary" disabled={busy || !name.trim()}>{busy ? '正在处理…' : editing ? '保存姓名' : '开始答题'}</Button>
          {editing && <Button type="button" variant="outline" disabled={busy} onClick={() => setEditing(false)}>取消</Button>}
        </form>
      </Dialog.Surface>
    </Dialog.Root>
    {attempt && !invalidSession && <>
      {submitted ? <section className="classroom-notice" role="status"><strong>提交成功</strong><p>{attempt.submitted_at && new Date(attempt.submitted_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })} · 答卷已锁定</p></section> : <p className="classroom-notice">已完成 {completed} / {attempt.quiz.questions.length} 题 · 提交后显示答案与解析。{closed ? ' 练习已关闭，草稿已保留，请联系老师。' : ''}</p>}
      <section className="quiz-card-list">{attempt.quiz.questions.map((q, index) => {
        const selected = submitted ? attempt.answers[q.id]?.selected_option_id : answers[q.id];
        return <article id={`question-${q.id}`} className="quiz-card" key={q.id}><header><span>{String(index + 1).padStart(2, '0')}</span><em>{q.type === 'judgement' ? '判断题' : '单选题'}</em></header><h2>{q.prompt}</h2>
          <div className="quiz-options" role="radiogroup" aria-label={q.prompt}>{q.options.map(o => <Button variant="unstyled" key={o.id} type="button" role="radio" aria-checked={selected === o.id} disabled={submitted || busy || closed} className={`${selected === o.id ? 'selected' : ''} ${submitted && q.correct_option_ids?.includes(o.id) ? 'correct' : ''} ${submitted && selected === o.id && !attempt.answers[q.id]?.is_correct ? 'wrong' : ''}`} onClick={() => setAnswers(values => ({ ...values, [q.id]: o.id }))}><span>{o.id}</span><strong>{o.text}</strong></Button>)}</div>
          {submitted && <div className="quiz-explanation"><strong>{attempt.answers[q.id]?.is_correct ? '回答正确' : `回答错误，正确答案：${q.correct_option_ids?.join('、')}`}</strong><p>{q.explanation}</p></div>}
        </article>;
      })}</section>
      {!submitted && <div className="classroom-submit-bar"><span>已完成 {completed} / {attempt.quiz.questions.length} 题</span><Button type="button" variant="primary" disabled={busy || closed} onClick={() => void submit()}>{busy ? '正在提交…' : '提交答卷'}</Button><small>提交成功后不可修改或重复提交。</small></div>}
    </>}
  </main>;
}
