"use client";
import { Button } from './ui/button';
import { InlineFeedback } from './ui/feedback';
import { EmptyState } from './ui/state';

import { useToast } from "./ui/toast";
import { Pagination } from "./ui/pagination";

import { useEffect, useState } from "react";
import * as Switch from "@radix-ui/react-switch";
import { boardApi, type BoardData, type BoardNotice, type BoardQuestion } from "../lib/community";
import styles from "./admin-community.module.css";

function Visibility({ checked, onChange, title, description }: { checked: boolean; onChange: (value: boolean) => void; title: string; description: string }) {
  return <div className={styles.visibility}><div><strong>{title}</strong><span>{description}</span></div><Switch.Root className={styles.toggle} checked={checked} onCheckedChange={onChange} aria-label={title}><Switch.Thumb className={styles.thumb} /></Switch.Root></div>;
}

function SaveStatus({ message, error }: { message: string; error: boolean }) {
  return message ? <p className={error ? styles.error : styles.success} role={error ? "alert" : "status"}>{message}</p> : null;
}

function NoticeEditor({ notice, saved }: { notice?: BoardNotice; saved: () => void }) {
  const notify = useToast();
  const [title, setTitle] = useState(notice?.title || "");
  const [content, setContent] = useState(notice?.content || "");
  const [published, setPublished] = useState(notice?.published ?? true);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [failed, setFailed] = useState(false);
  return <form className={styles.noticeForm} aria-label={notice ? `编辑公告：${notice.title}` : "新公告"} onSubmit={async event => {
    event.preventDefault(); setBusy(true); setStatus(""); setFailed(false);
    try {
      await boardApi(`/admin/community/announcements${notice ? `/${notice.id}` : ""}`, { method: notice ? "PUT" : "POST", body: JSON.stringify({ title: title.trim(), content: content.trim(), published }) });
      if (!notice) { setTitle(""); setContent(""); }
      notify(published ? "公告已发布" : "公告已保存，仅管理员可见", "success"); saved();
    } catch (reason) { setFailed(true); setStatus(reason instanceof Error ? reason.message : "保存失败，请重试"); }
    finally { setBusy(false); }
  }}><fieldset disabled={busy}>
    <label className={styles.field}><span>公告标题</span><input value={title} maxLength={100} placeholder="为这条消息起一个清楚的标题" required onChange={event => setTitle(event.target.value)} /></label>
    <label className={styles.field}><span>公告正文 <small>{content.length} / 2000</small></span><textarea className={styles.noticeContent} value={content} maxLength={2000} placeholder="写下产品更新、活动安排，或想告诉用户的事。" required onChange={event => setContent(event.target.value)} /></label>
    <Visibility checked={published} onChange={setPublished} title="公开展示" description="开启后展示在用户的公告弹窗中" />
    <div className={styles.formFooter}><SaveStatus message={status} error={failed} /><Button variant="unstyled" className={styles.primaryButton} type="submit" disabled={!title.trim() || !content.trim()}>{busy ? "保存中…" : notice ? "保存修改" : published ? "发布公告" : "保存草稿"}</Button></div>
  </fieldset></form>;
}

function ReplyEditor({ question, saved }: { question: BoardQuestion; saved: () => void }) {
  const notify = useToast();
  const suggestion = question.kind === "SUGGESTION";
  const [answer, setAnswer] = useState(question.answer || "");
  const [published, setPublished] = useState(!suggestion && Boolean(question.published));
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [failed, setFailed] = useState(false);
  return <article className={styles.messageCard}>
    <div className={styles.messageHeader}><span className={`${styles.kind} ${suggestion ? styles.suggestionKind : ""}`}>{suggestion ? "建议与批评" : "提问"}</span><span className={`${styles.state} ${question.published ? styles.publicState : !question.answer ? styles.pendingState : ""}`}>{question.published ? "已公开" : question.answer ? "已回复" : "待回复"}</span></div>
    <div className={styles.messageMeta}><span>{question.author_name || "创作者"}</span><time>{question.created_at.slice(0, 10).replaceAll("-", ".")}</time></div>
    <p className={styles.messageText}>{question.question}</p>
    <form aria-label={`回复：${question.question}`} onSubmit={async event => {
      event.preventDefault(); setBusy(true); setStatus(""); setFailed(false);
      try { await boardApi(`/admin/community/questions/${question.id}`, { method: "PUT", body: JSON.stringify({ answer, published: !suggestion && published }) }); notify("答复已保存", "success"); saved(); }
      catch (reason) { setFailed(true); setStatus(reason instanceof Error ? reason.message : "保存失败，请重试"); }
      finally { setBusy(false); }
    }}><fieldset disabled={busy}><label className={styles.field}><span>管理员答复</span><textarea value={answer} maxLength={4000} placeholder="写下你的答复…" onChange={event => setAnswer(event.target.value)} /></label>
      {suggestion ? <div className={styles.privateNote}><svg viewBox="0 0 20 20" aria-hidden="true"><rect x="4" y="8" width="12" height="9" rx="2" /><path d="M6 8V5a4 4 0 0 1 8 0v3" /></svg>回复仅提交者可见</div> : <Visibility checked={published} onChange={setPublished} title="公开为精选问答" description="公开后所有人可阅读，提问者信息会隐藏" />}
      {published && !answer.trim() && <p className={styles.validation}>请先填写答复，再公开这条问答。</p>}
      <div className={styles.formFooter}><SaveStatus message={status} error={failed} /><Button variant="unstyled" type="submit" className={styles.primaryButton} disabled={published && !answer.trim()}>{busy ? "保存中…" : "保存答复"}</Button></div>
    </fieldset></form>
  </article>;
}

type MessageFilter = "ALL" | "PENDING" | "QUESTION" | "SUGGESTION";
const filters: Array<[MessageFilter, string]> = [["ALL", "全部"], ["PENDING", "待回复"], ["QUESTION", "提问"], ["SUGGESTION", "建议与批评"]];

export default function AdminCommunity() {
  const [data, setData] = useState<BoardData | null>(null);
  const [error, setError] = useState("");
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<MessageFilter>("ALL");
  const saved = () => setRevision(value => value + 1);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError("");
    void boardApi<BoardData>(`/admin/community?offset=${offset}`, { signal: controller.signal }).then(setData).catch(reason => { if (!controller.signal.aborted) setError(reason.message); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [offset, revision]);
  const questions = data?.questions || [];
  const visible = questions.filter(question => filter === "ALL" || (filter === "PENDING" ? !question.answer : (question.kind || "QUESTION") === filter));
  const pending = questions.filter(question => !question.answer).length;
  return <section className={styles.panel} aria-label="公告与问答管理">
    <header className={styles.heading}><div><h2>公告与问答</h2><p>发布平台消息，处理用户的提问与反馈。</p></div><Button variant="unstyled" className={styles.secondaryButton} type="button" onClick={saved} disabled={loading}>刷新</Button></header>
    {error && <InlineFeedback as="div" className={styles.loadError} >{error}<Button variant="unstyled" className={styles.secondaryButton} type="button" onClick={saved}>重试</Button></InlineFeedback>}
    <div className={styles.columns}>
      <aside className={styles.noticeColumn} aria-labelledby="admin-notice-title">
        <div className={styles.columnHeading}><h3 id="admin-notice-title">公告</h3><span>用户端展示最新 3 条公开公告</span></div>
        <div className={styles.newNotice}><div className={styles.cardHeading}><h4>新公告</h4><span>WHAT’S NEW</span></div><NoticeEditor saved={saved} /></div>
        {Boolean(data?.announcements.length) && <div className={styles.savedNotices}><h4>已保存的公告</h4>{data?.announcements.map(notice => <details className={styles.noticeItem} key={notice.id}><summary><div><strong>{notice.title}</strong><span>{notice.created_at.slice(0, 10)} · {notice.published ? "已公开" : "仅管理员可见"}</span></div><span className={styles.editLabel}>编辑</span></summary><NoticeEditor notice={notice} saved={saved} /></details>)}</div>}
      </aside>
      <section className={styles.inbox} aria-labelledby="admin-inbox-title">
        <div className={styles.columnHeading}><h3 id="admin-inbox-title">用户留言</h3><span>{loading && !data ? "正在加载…" : `本页 ${questions.length} 条 · ${pending} 条待回复`}</span></div>
        <div className={styles.filters} role="group" aria-label="筛选本页留言">{filters.map(([value, label]) => <Button variant="unstyled" key={value} type="button" aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</Button>)}</div>
        <div className={styles.messageList} aria-busy={loading}>{visible.map(question => <ReplyEditor key={question.id} question={question} saved={saved} />)}{!loading && !error && !visible.length && <EmptyState className={styles.empty}><strong>{questions.length ? "本页没有符合条件的留言" : "暂时没有用户留言"}</strong><p>{questions.length ? "试试其他筛选，或查看下一页。" : "用户提交的提问和建议会显示在这里。"}</p></EmptyState>}</div>
        <Pagination className={styles.pagination} buttonClassName={styles.secondaryButton} ariaLabel="留言分页" layout="trailing-actions" page={offset / 20 + 1} hasMore={Boolean(data?.has_more)} disabled={loading} onPageChange={page => setOffset((page - 1) * 20)} />
      </section>
    </div>
  </section>;
}
