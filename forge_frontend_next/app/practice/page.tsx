"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { AccountMenu } from "../../components/account-menu";
import { Button } from "../../components/ui/button";
import { forgeApi, ApiError } from "../../lib/api-client";
import styles from "./practice.module.css";
import AnimationPreview from "./animation-preview";

type Message = { role: "user" | "assistant"; content: string };
type Reply = { id: string; output: string; duration_ms?: number };
type Animation = { id: string; status: string; phase?: string; attempts?: number; output?: string; error?: string; artifact_id?: string };
const examples = ["给初中生设计一个串联电路演示，说明开关与两盏灯的关系。", "怎样用一个可操作的滑轮演示，讲清省力与距离的关系？", "把水波干涉设计成课堂演示，学生可以调节哪些参数？"];

export default function PracticePage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loginRequired, setLoginRequired] = useState(false);
  const [loggedIn, setLoggedIn] = useState(false);
  const [authReady, setAuthReady] = useState(false);
  const [progress, setProgress] = useState("");
  const [preview, setPreview] = useState<{ html: string; artifactId: string } | null>(null);
  const alive = useRef(true);
  const pending = useRef(false);
  const end = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);

  useEffect(() => {
    let active = true;
    forgeApi<{ auth_type?: string }>("/auth/me").then(user => {
      if (active) { setLoggedIn(user.auth_type === "sso"); setLoginRequired(user.auth_type !== "sso"); }
    }).catch(() => { if (active) setLoginRequired(true); }).finally(() => { if (active) setAuthReady(true); });
    return () => { active = false; };
  }, []);
  useEffect(() => { if (messages.length || busy) end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages, busy]);

  async function send(animation = false) {
    const prompt = draft.trim();
    if (!prompt || pending.current || !loggedIn) return;
    const history = messages;
    if (history.length >= 20 || history.reduce((n, m) => n + m.content.length, prompt.length) > 36000) {
      setError("当前对话较长，请开始新对话后继续。"); return;
    }
    pending.current = true;
    setBusy(true); setError(""); setProgress(animation ? "正在设计动画…" : "");
    setMessages([...history, { role: "user", content: prompt }]); setDraft("");
    try {
      const body = JSON.stringify({ prompt, history });
      let reply: Reply;
      if (animation) {
        let task = await forgeApi<Animation>("/nar-agent/animations", { method: "POST", headers: { "X-NarAgent-Action": "chat" }, body });
        const started = Date.now();
        while (task.status === "RUNNING") {
          if (Date.now() - started > 930000) throw new Error("等待超时，请联系管理员查看任务状态。");
          await new Promise(resolve => setTimeout(resolve, 2000));
          if (!alive.current) return;
          task = await forgeApi<Animation>(`/nar-agent/animations/${task.id}`);
          const phases: Record<string, string> = { DESIGNING: "正在设计与编写动画", BUILDING: "正在隔离环境构建与检查", CHECKING: "正在检查并修复", FINALIZING: "正在整理成品" };
          setProgress(`${phases[task.phase || ""] || "正在制作动画"} · 第 ${task.attempts || 0} 次构建`);
        }
        if (task.status !== "SUCCEEDED" || !task.artifact_id) throw new Error(task.error || "动画未通过检查，请调整要求后重试。");
        const blob = await forgeApi.blob(`/nar-agent/artifacts/${task.artifact_id}/index.html`);
        setPreview({ html: await blob.text(), artifactId: task.artifact_id });
        reply = { id: task.id, output: task.output || "动画已生成，可在下方操作演示。" };
      } else reply = await forgeApi<Reply>("/nar-agent/chat", {
        method: "POST", headers: { "X-NarAgent-Action": "chat" }, body: JSON.stringify({ prompt, history }),
      });
      setMessages([...history, { role: "user", content: prompt }, { role: "assistant", content: reply.output }]);
    } catch (cause) {
      setMessages(history); setDraft(prompt);
      if (cause instanceof ApiError && cause.status === 401) { setLoginRequired(true); setLoggedIn(false); }
      setError(cause instanceof Error ? cause.message : "发送失败，请稍后重试。");
    } finally { pending.current = false; setBusy(false); setProgress(""); input.current?.focus(); }
  }

  return <main className={styles.page}>
    <header className={styles.header}><Link href="/" className={styles.brand}>NarrativeOS <span>／ 讲练工具</span></Link><AccountMenu /></header>
    <div className={styles.layout}>
      <aside className={styles.sidebar}><p className={styles.eyebrow}>TEACHING STUDIO</p><h1>讲练工具</h1><div className={styles.activeTool}><span aria-hidden="true">✦</span><div>临场动画<small>先把知识变成可演示的想法</small></div></div><Button onClick={() => { setMessages([]); setDraft(""); setError(""); setPreview(null); input.current?.focus(); }} disabled={busy}>＋ 开始新对话</Button><p className={styles.note}>先对话完善思路，或选择制作动画。制作通常需要等待数分钟。<br /><br />对话仅保留在当前页面，刷新后清空。</p></aside>
      <section className={styles.chat} aria-label="临场动画教学助手">
        <div className={styles.chatHeader}><div><strong>临场动画</strong><span>和教学助手一起，拆解一个知识点。</span></div><span className={styles.badge}>方案对话</span></div>
        <div className={styles.conversation}>
          {messages.length === 0 && <div className={styles.empty}><span className={styles.spark} aria-hidden="true">✦</span><p className={styles.eyebrow}>从一个课堂问题开始</p><h2>你想让学生<br />看懂什么？</h2><p>告诉我知识点、学生学段和想观察的现象。我们可以一起完善演示思路、参数与交互。</p><div className={styles.examples}>{examples.map((example, i) => <button key={example} type="button" onClick={() => { setDraft(example); input.current?.focus(); }}><span>0{i + 1}</span>{example}<b aria-hidden="true">↗</b></button>)}</div></div>}
          {messages.map((message, i) => <article key={i} className={`${styles.message} ${message.role === "user" ? styles.user : styles.assistant}`}><span className={styles.speaker}>{message.role === "user" ? "你" : "教学助手"}</span><div>{message.content}</div></article>)}
          {preview && <AnimationPreview html={preview.html} artifactId={preview.artifactId} />}
          {busy && <p role="status" className={styles.thinking}>{progress || "教学助手正在思考，请稍候…"}</p>}
          <div ref={end} />
        </div>
        <div className={styles.composerArea}>
          {loginRequired && <p role="status" className={styles.notice}>请通过右上角账号菜单登录 NarrativeOS，再使用讲练助手。登录后可刷新页面。</p>}
          {error && <p role="alert" className={styles.error}>{error}</p>}
          <form className={styles.composer} onSubmit={event => { event.preventDefault(); void send(); }}>
            <label htmlFor="teaching-prompt" className="sr-only">输入教学问题</label>
            <textarea id="teaching-prompt" ref={input} value={draft} onChange={event => setDraft(event.target.value)} maxLength={12000} rows={3} placeholder="例如：用串联电路讲解电流，学生可以点击开关…" disabled={busy} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(); } }} />
            <div><small>Enter 发送 · Shift + Enter 换行</small><span className={styles.actions}><Button onClick={() => { void send(true); }} disabled={busy || !authReady || !loggedIn || !draft.trim()}>制作动画</Button><Button type="submit" variant="primary" disabled={!authReady || !loggedIn || !draft.trim()} busy={busy}>{busy ? "处理中" : "发送 ↗"}</Button></span></div>
          </form>
          <p className={styles.disclaimer}>生成内容用于备课参考，课堂使用前请核对知识与参数。</p>
        </div>
      </section>
    </div>
  </main>;
}
