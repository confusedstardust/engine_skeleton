"use client";

import { ArrowUpRight, Send, Sparkles } from "lucide-react";
import { Button } from "../../components/ui/button";
import { LoadingState, Spinner } from "../../components/ui/state";
import CreationTimeline from "./creation-timeline";
import GeneratedWorkCard from "./generated-work-card";
import MessageMarkdown from "./message-markdown";
import type { usePracticeWorkspace } from "./use-practice-workspace";
import styles from "./practice.module.css";

type Workspace = ReturnType<typeof usePracticeWorkspace>;
const examples = [
  "把《赤壁赋》做成可以抽背的互动网页。",
  "生成一个适合初中生操作的串并联电路实验。",
  "设计一个知识闯关网页，答完题才能进入下一关。",
];

/** Chat, timeline and composer render only; all business actions come from the workspace hook. */
export default function PracticeChat({ workspace }: { workspace: Workspace }) {
  const {
    workspaceScope, messages, draft, setDraft, busy, error, loginRequired, loggedIn,
    sessionReady, authReady, progress, activeTask, workPreviews, currentArtifactId,
    setSelectedArtifactId, setCurrentArtifactId, end, input, send, savedCardWorkId,
    serverEnabled, serverChecked, conversationId, conversationTitle,
    olderCursor, loadOlder, loadingOlder, chatScroll, openArtifact,
  } = workspace;
  const canSubmit = Boolean(!busy && authReady && sessionReady && serverChecked && loggedIn && (!conversationId || serverEnabled) && draft.trim());

  return <section className={styles.chat} aria-label="NarrativeOS 互动学习创作助手">
    <div className={styles.chatHeader}>
      <div><strong>{conversationTitle || "互动学习创作"}</strong><span>用自然语言制作可操作、可修改的学习体验。</span></div>
      <span className={styles.badge}>方案对话</span>
    </div>
    <div className={styles.conversation} ref={chatScroll}>
      {conversationId && olderCursor !== null && <div className={styles.olderHistory}>
        <Button variant="ghost" size="sm" onClick={() => { void loadOlder(); }}
          disabled={loadingOlder}>{loadingOlder ? "加载中…" : "查看更早的消息"}</Button>
      </div>}
      {!sessionReady && <LoadingState inline className={styles.thinking}>正在恢复作品会话…</LoadingState>}
      {sessionReady && messages.length === 0 && <div className={styles.empty}>
        <span className={styles.spark} aria-hidden="true"><Sparkles size={33} strokeWidth={1.5} /></span>
        <p className={styles.eyebrow}>从一个学习问题开始</p>
        <h2>{workspaceScope === "general" ? "你想制作什么互动学习体验？" : "继续这次学习创作"}</h2>
        <p>{workspaceScope === "general"
          ? "描述学科、年级、玩法或参考模板。可以生成练习卡、实验模拟与互动学习网页。"
          : conversationId ? "这个会话还没有消息，你可以开始创作。" : "这件作品没有可恢复的独立对话记录，但已经保存的作品及版本仍可打开、预览和继续修改。"}</p>
        <div className={styles.examples}>
          {examples.map((example, i) => <Button key={example} variant="unstyled" onClick={() => {
            setDraft(example);
            input.current?.focus();
          }}>
            <span>0{i + 1}</span>{example}<ArrowUpRight size={16} strokeWidth={1.7} aria-hidden="true" />
          </Button>)}
        </div>
      </div>}
      {sessionReady && messages.map((message, i) => <article key={i}
        className={`${styles.message} ${message.role === "user" ? styles.user : styles.assistant}`}>
        <span className={styles.speaker}>{message.role === "user" ? "你" : "教学助手"}</span>
        <div>
          {message.timeline?.length ? <CreationTimeline timeline={message.timeline}
            elapsedMs={message.durationMs} learningPlan={message.learningPlan}
            publicBrief={message.publicBrief} /> : null}
          {message.role === "assistant" ? <MessageMarkdown content={message.content} /> : message.content}
          {message.work && <GeneratedWorkCard work={message.work}
            savedWorkId={savedCardWorkId(message.work)}
            onOpen={id => {
              if (conversationId) void openArtifact(id);
              else { setSelectedArtifactId(id); setCurrentArtifactId(id); }
            }} />}
        </div>
      </article>)}
      {busy && <div className={styles.runningBlock}>
        <div role="status" aria-live="polite" className={styles.thinking}>
          <Spinner size="sm" tone="accent" />
          <span>{progress || (activeTask ? "正在制作你的学习作品…" : "正在理解学习需求…")}</span>
        </div>
        {activeTask?.timeline?.length ? <CreationTimeline timeline={activeTask.timeline}
          elapsedMs={activeTask.elapsed_ms} learningPlan={activeTask.learning_plan}
          publicBrief={activeTask.public_brief}
          briefStreaming={activeTask.public_brief_state === "STREAMING"} active /> : null}
      </div>}
      <div ref={end} />
    </div>
    <div className={styles.composerArea}>
      {loginRequired && <p role="status" className={styles.notice}>
        请通过左侧栏的账号入口登录 NarrativeOS，再使用创作助手。
      </p>}
      {error && <p role="alert" className={styles.error}>{error}</p>}
      <form className={styles.composer} onSubmit={event => { event.preventDefault(); void send(); }}>
        <label htmlFor="teaching-prompt" className="sr-only">输入学习问题</label>
        <textarea id="teaching-prompt" ref={input} value={draft} onChange={event => setDraft(event.target.value)}
          maxLength={12000} rows={3} placeholder="例如：用串联电路讲解电流，学生可以点击开关…"
          disabled={busy} onKeyDown={event => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault(); void send();
            }
          }} />
        <div>
          <small>Enter 发送 · Shift + Enter 换行</small>
          <span className={styles.actions}>
            <Button onClick={() => { void send("animation"); }} disabled={!canSubmit}>制作动画</Button>
            <Button onClick={() => { void send("html"); }} disabled={!canSubmit}>生成 HTML</Button>
            {currentArtifactId && workPreviews[currentArtifactId]?.kind === "html" &&
              <Button onClick={() => { void send("edit"); }} disabled={!canSubmit}>修改当前作品</Button>}
            <Button type="submit" variant="primary" disabled={!canSubmit} busy={busy}>
              {busy ? "处理中" : <>发送 <Send size={15} strokeWidth={1.7} aria-hidden="true" /></>}
            </Button>
          </span>
        </div>
      </form>
      <p className={styles.disclaimer}>AI 生成内容使用前请核对知识准确性与交互流程。</p>
    </div>
  </section>;
}

