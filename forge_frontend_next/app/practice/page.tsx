"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { AccountMenu } from "../../components/account-menu";
import { Button } from "../../components/ui/button";
import { forgeApi, ApiError } from "../../lib/api-client";
import styles from "./practice.module.css";
import AnimationPreview from "./animation-preview";
import MessageMarkdown from "./message-markdown";
import CreationTimeline, { type TimelineEvent } from "./creation-timeline";

type Message = { role: "user" | "assistant"; content: string; timeline?: TimelineEvent[]; durationMs?: number };
type Reply = { id: string; output: string; duration_ms?: number };
type BuildTask = { id: string; status: string; phase?: string; attempts?: number; output?: string; error?: string; artifact_id?: string; timeline?: TimelineEvent[]; elapsed_ms?: number; learning_plan?: { learning_goal: string; interaction_method: string; key_concepts: string[] } };
const examples = ["把《赤壁赋》做成可以抽背的互动网页。", "生成一个适合初中生操作的串并联电路实验。", "设计一个知识闯关网页，答完题才能进入下一关。"];

export default function PracticePage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loginRequired, setLoginRequired] = useState(false);
  const [loggedIn, setLoggedIn] = useState(false);
  const [authReady, setAuthReady] = useState(false);
  const [progress, setProgress] = useState("");
  const [activeTask, setActiveTask] = useState<BuildTask | null>(null);
  const [preview, setPreview] = useState<{ html: string; artifactId: string; kind: "html" | "animation" } | null>(null);
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

  async function send(mode: "chat" | "animation" | "html" | "edit" = "chat") {
    const prompt = draft.trim();
    if (!prompt || pending.current || !loggedIn) return;
    const history = messages.map(message => ({ role: message.role, content: message.content }));
    const originalMessages = messages;
    let lastTask: BuildTask | undefined;
    if (history.length >= 20 || history.reduce((n, m) => n + m.content.length, prompt.length) > 36000) {
      setError("当前对话较长，请开始新对话后继续。"); return;
    }
    pending.current = true;
    setBusy(true); setError(""); setProgress(mode === "animation" ? "正在设计动画…" : mode === "chat" ? "" : "正在制作互动网页…");
    setMessages([...originalMessages, { role: "user", content: prompt }]); setDraft("");
    try {
      const parentArtifact = mode === "edit" && preview?.kind === "html" ? preview.artifactId : null;
      const body = JSON.stringify({ prompt, history, ...(parentArtifact ? { parent_artifact_id: parentArtifact } : {}) });
      let reply: Reply;
      if (mode !== "chat") {
        const endpoint = mode === "animation" ? "animations" : "html";
        let task = await forgeApi<BuildTask>(`/nar-agent/${endpoint}`, { method: "POST", headers: { "X-NarAgent-Action": "chat" }, body });
        lastTask = task; setActiveTask(task);
        const started = Date.now();
        while (task.status === "RUNNING") {
          if (Date.now() - started > 930000) throw new Error("等待超时，请联系管理员查看任务状态。");
          await new Promise(resolve => setTimeout(resolve, 2000));
          if (!alive.current) return;
          task = await forgeApi<BuildTask>(`/nar-agent/${endpoint}/${task.id}`);
          lastTask = task; setActiveTask(task);
          const phases: Record<string, string> = { DESIGNING: "正在理解学习需求", PLANNING: "正在规划学习交互", DRAFTING: "正在制作互动内容", BUILDING: "正在组装互动作品", CHECKING: "正在检查作品", FINALIZING: "正在整理作品" };
          setProgress(phases[task.phase || ""] || "正在制作互动学习作品");
        }
        if (task.status !== "SUCCEEDED" || !task.artifact_id) throw new Error(task.error || "作品未通过检查，请调整要求后重试。");
        const blob = await forgeApi.blob(`/nar-agent/artifacts/${task.artifact_id}/index.html`);
        setPreview({ html: await blob.text(), artifactId: task.artifact_id, kind: mode === "animation" ? "animation" : "html" });
        reply = { id: task.id, output: task.output || "作品已经做好，可以打开预览并继续修改。" };
      } else reply = await forgeApi<Reply>("/nar-agent/chat", {
        method: "POST", headers: { "X-NarAgent-Action": "chat" }, body: JSON.stringify({ prompt, history }),
      });
      setMessages([...originalMessages, { role: "user", content: prompt }, { role: "assistant", content: reply.output, timeline: lastTask?.timeline, durationMs: lastTask?.elapsed_ms }]);
    } catch (cause) {
      if (mode === "chat") setMessages(originalMessages);
      else setMessages([...originalMessages, { role: "user", content: prompt }, { role: "assistant", content: "本次作品没有完成。你可以调整需求后再次尝试。", timeline: lastTask?.timeline, durationMs: lastTask?.elapsed_ms }]);
      setDraft(prompt);
      if (cause instanceof ApiError && cause.status === 401) { setLoginRequired(true); setLoggedIn(false); }
      setError(cause instanceof Error ? cause.message : "发送失败，请稍后重试。");
    } finally { pending.current = false; setBusy(false); setActiveTask(null); setProgress(""); input.current?.focus(); }
  }

  return <main className={styles.page}>
    <header className={styles.header}><Link href="/" className={styles.brand}>NarrativeOS <span>／ 讲练工具</span></Link><AccountMenu /></header>
    <div className={styles.layout}>
      <aside className={styles.sidebar}><p className={styles.eyebrow}>TEACHING STUDIO</p><h1>讲练工具</h1><div className={styles.activeTool}><span aria-hidden="true">✦</span><div>互动学习创作<small>生成、测试与继续修改 HTML 作品</small></div></div><Button onClick={() => { setMessages([]); setDraft(""); setError(""); setPreview(null); input.current?.focus(); }} disabled={busy}>＋ 开始新对话</Button><p className={styles.note}>可以直接生成互动网页，或制作教学动画。作品保存为独立版本；当前聊天刷新后清空。</p></aside>
      <section className={styles.chat} aria-label="NarrativeOS 互动学习创作助手">
        <div className={styles.chatHeader}><div><strong>互动学习创作</strong><span>用自然语言制作可操作、可修改的教学网页。</span></div><span className={styles.badge}>方案对话</span></div>
        <div className={styles.conversation}>
          {messages.length === 0 && <div className={styles.empty}><span className={styles.spark} aria-hidden="true">✦</span><p className={styles.eyebrow}>从一个课堂问题开始</p><h2>你想制作什么<br />互动学习体验？</h2><p>描述学科、年级、玩法或参考模板。可以生成练习卡、实验模拟与互动学习网页。</p><div className={styles.examples}>{examples.map((example, i) => <button key={example} type="button" onClick={() => { setDraft(example); input.current?.focus(); }}><span>0{i + 1}</span>{example}<b aria-hidden="true">↗</b></button>)}</div></div>}
          {messages.map((message, i) => <article key={i} className={`${styles.message} ${message.role === "user" ? styles.user : styles.assistant}`}><span className={styles.speaker}>{message.role === "user" ? "你" : "教学助手"}</span><div>{message.timeline?.length ? <CreationTimeline timeline={message.timeline} elapsedMs={message.durationMs} /> : null}{message.role === "assistant" ? <MessageMarkdown content={message.content} /> : message.content}</div></article>)}
          {preview && <AnimationPreview html={preview.html} artifactId={preview.artifactId} label={preview.kind === "html" ? "HTML 互动学习作品" : "动画成品预览"} />}
          {busy && (activeTask?.timeline?.length ? <CreationTimeline timeline={activeTask.timeline} elapsedMs={activeTask.elapsed_ms} active /> : <p role="status" className={styles.thinking}>{progress || "正在理解学习需求…"}</p>)}
          <div ref={end} />
        </div>
        <div className={styles.composerArea}>
          {loginRequired && <p role="status" className={styles.notice}>请通过右上角账号菜单登录 NarrativeOS，再使用讲练助手。登录后可刷新页面。</p>}
          {error && <p role="alert" className={styles.error}>{error}</p>}
          <form className={styles.composer} onSubmit={event => { event.preventDefault(); void send(); }}>
            <label htmlFor="teaching-prompt" className="sr-only">输入教学问题</label>
            <textarea id="teaching-prompt" ref={input} value={draft} onChange={event => setDraft(event.target.value)} maxLength={12000} rows={3} placeholder="例如：用串联电路讲解电流，学生可以点击开关…" disabled={busy} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(); } }} />
            <div><small>Enter 发送 · Shift + Enter 换行</small><span className={styles.actions}><Button onClick={() => { void send("animation"); }} disabled={busy || !authReady || !loggedIn || !draft.trim()}>制作动画</Button><Button onClick={() => { void send("html"); }} disabled={busy || !authReady || !loggedIn || !draft.trim()}>生成 HTML</Button>{preview?.kind === "html" && <Button onClick={() => { void send("edit"); }} disabled={busy || !authReady || !loggedIn || !draft.trim()}>修改当前作品</Button>}<Button type="submit" variant="primary" disabled={!authReady || !loggedIn || !draft.trim()} busy={busy}>{busy ? "处理中" : "发送 ↗"}</Button></span></div>
          </form>
          <p className={styles.disclaimer}>生成内容用于备课参考，课堂使用前请核对知识与参数。</p>
        </div>
      </section>
    </div>
  </main>;
}
