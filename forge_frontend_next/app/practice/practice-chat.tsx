"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUpRight, Send, Sparkles } from "lucide-react";
import { Button } from "../../components/ui/button";
import { LoadingState } from "../../components/ui/state";
import CreationTimeline from "./creation-timeline";
import AgentChoicePrompt from "./agent-choice-prompt";
import { parseAgentChoiceMessage, visibleAgentChoicePrefix } from "./agent-choice-protocol";
import GeneratedWorkCard from "./generated-work-card";
import MessageMarkdown from "./message-markdown";
import PracticeMessageAvatar from "./practice-message-avatar";
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
    sessionReady, authReady,
    setSelectedArtifactId, setCurrentArtifactId, end, input, send, savedCardWorkId,
    serverReady, serverChecked, conversationId, conversationTitle, streamText,
    olderCursor, loadOlder, loadingOlder, chatScroll, openArtifact,
    userAvatarUrl, userInitial,
  } = workspace;
  const canAnswer = Boolean(!busy && authReady && sessionReady && serverChecked && serverReady && loggedIn);
  const canSubmit = Boolean(canAnswer && draft.trim());
  const [burstKeys, setBurstKeys] = useState<string[]>([]);
  const seen = useRef<{ conversationId?: string; lastKey?: string; initialized: boolean }>({ initialized: false });

  // Only celebrate messages newly appended to the visible conversation, not
  // restored history or older pages prepended by "load more".
  useEffect(() => {
    if (!sessionReady) { seen.current.initialized = false; return; }
    const last = messages[messages.length - 1];
    const lastKey = last ? last.id ?? `message-${last.seq ?? messages.length - 1}-${last.role}` : undefined;
    const previous = seen.current;
    if (!previous.initialized || previous.conversationId !== conversationId) {
      const justCreated = !previous.conversationId && Boolean(conversationId)
        && busy && messages.length === 1 && last?.role === "user";
      setBurstKeys(justCreated && lastKey ? [lastKey] : []);
      seen.current = { initialized: true, conversationId, lastKey };
      return;
    }
    if (lastKey && lastKey !== previous.lastKey) {
      setBurstKeys(current => current.includes(lastKey) ? current : [...current.slice(-3), lastKey]);
    }
    previous.lastKey = lastKey;
  }, [messages, conversationId, sessionReady, busy]);

  return <section className={styles.chat} aria-label="NarrativeOS 互动学习创作助手">
    <div className={styles.chatHeader}>
      <div><strong>{conversationTitle || "互动学习创作"}</strong><span>用自然语言制作可操作、可修改的学习体验。</span></div>
      <span className={styles.badge}>智能助手</span>
    </div>
    <div className={styles.conversation} ref={chatScroll}>
      {conversationId && olderCursor !== null && <div className={styles.olderHistory}>
        <Button variant="ghost" size="sm" onClick={() => { void loadOlder(); }}
          disabled={loadingOlder}>{loadingOlder ? "加载中…" : "查看更早的消息"}</Button>
      </div>}
      {!sessionReady && <LoadingState inline className={styles.thinking}>正在从服务器读取会话…</LoadingState>}
      {sessionReady && messages.length === 0 && <div className={styles.empty}>
        <span className={styles.spark} aria-hidden="true"><Sparkles size={33} strokeWidth={1.5} /></span>
        <p className={styles.eyebrow}>从一个学习问题开始</p>
        <h2>{workspaceScope === "general" ? "今天想学习或创造什么？" : "继续这次学习创作"}</h2>
        <p>{workspaceScope === "general"
          ? "直接提问，或描述你想生成的练习、互动实验和学习网页；也可以继续修改已有作品。"
          : conversationId ? "这个会话还没有消息，你可以开始创作。" : "这是以前保存的作品，原对话若未曾上传服务器则无法恢复；你可以开启一段新的云端会话继续创作。"}</p>
        <div className={styles.examples}>
          {examples.map((example, i) => <Button key={example} variant="unstyled" onClick={() => {
            setDraft(example);
            input.current?.focus();
          }}>
            <span>0{i + 1}</span>{example}<ArrowUpRight size={16} strokeWidth={1.7} aria-hidden="true" />
          </Button>)}
        </div>
      </div>}
      {sessionReady && messages.map((message, i) => {
        const key = message.id ?? `message-${message.seq ?? i}-${message.role}`;
        const parsed = message.role === "assistant" ? parseAgentChoiceMessage(message.content) : null;
        const choice = message.choices ?? parsed?.choice;
        return <article key={key}
          className={`${styles.message} ${message.role === "user" ? styles.user : styles.assistant}`}
          aria-label={message.role === "user" ? "用户消息" : "助手消息"}>
          <PracticeMessageAvatar role={message.role} userAvatarUrl={userAvatarUrl}
            userInitial={userInitial} burst={burstKeys.includes(key)} />
          <div className={styles.messagePaper}>
            {message.timeline?.length ? <CreationTimeline timeline={message.timeline}
              elapsedMs={message.durationMs} learningPlan={message.learningPlan}
              publicBrief={message.publicBrief} /> : null}
            {message.role === "assistant" ? <>
              {parsed?.body ? <MessageMarkdown content={parsed.body} /> : null}
              {choice && <AgentChoicePrompt choice={choice} disabled={!canAnswer || i !== messages.length - 1}
                onAnswer={answer => { void send(answer); }} />}
            </> : message.content}
            {message.work && <GeneratedWorkCard work={message.work}
              savedWorkId={savedCardWorkId(message.work)}
              onOpen={id => {
                if (conversationId) void openArtifact(id);
                else { setSelectedArtifactId(id); setCurrentArtifactId(id); }
              }} />}
          </div>
        </article>;
      })}
      {streamText && <article className={`${styles.message} ${styles.assistant}`}
        aria-label="助手正在流式回复">
        <PracticeMessageAvatar role="assistant" />
        <div className={styles.messagePaper}><MessageMarkdown content={visibleAgentChoicePrefix(streamText)} /></div>
      </article>}
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

