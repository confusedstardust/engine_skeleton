"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowUpRight, Box, ClipboardCheck, Gamepad2, LayoutTemplate, Play, Send, Sparkles, WandSparkles, X } from "lucide-react";
import * as ScrollArea from "@radix-ui/react-scroll-area";
import { Button } from "../../components/ui/button";
import { LoadingState } from "../../components/ui/state";
import CreationTimeline from "./creation-timeline";
import AgentChoicePrompt from "./agent-choice-prompt";
import { parseAgentChoiceMessage, visibleAgentChoicePrefix } from "./agent-choice-protocol";
import GeneratedWorkCard from "./generated-work-card";
import RpgTaskCard from "./rpg-task-card";
import { withBasePath } from "../base-path";
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
const formats = [
  { label: "互动课件", Icon: LayoutTemplate, placeholder: "描述要做成互动课件的知识点，例如「让学生拖动砝码探索杠杆平衡」" },
  { label: "教学动画", Icon: Play, placeholder: "描述要用动画讲清楚的过程，例如「演示月相如何变化」" },
  { label: "课后练习", Icon: ClipboardCheck, placeholder: "描述要练习的知识点和年级，例如「为初一设计整数加减练习」" },
  { label: "RPG课堂游戏", Icon: Gamepad2, placeholder: "描述学习目标和游戏情境，例如「扮演水滴，探索水循环」" },
  { label: "3D演示", Icon: Box, placeholder: "描述想从不同角度观察的对象，例如「观察地球自转与昼夜变化」" },
];

/** Chat, timeline and composer render only; all business actions come from the workspace hook. */
export default function PracticeChat({ workspace }: { workspace: Workspace }) {
  const {
    workspaceScope, messages, draft, setDraft, busy, error, loginRequired, loggedIn,
    creationFormat, setCreationFormat, draftLimit,
    sessionReady, authReady, progress, activeTask,
    setSelectedArtifactId, setCurrentArtifactId, end, input, send, savedCardWorkId,
    serverReady, serverChecked, conversationId, conversationTitle, streamText,
    olderCursor, loadOlder, loadingOlder, chatScroll, openArtifact,
    userAvatarUrl, userInitial,
  } = workspace;
  const canAnswer = Boolean(!busy && authReady && sessionReady && serverChecked && serverReady && loggedIn);
  const canSubmit = Boolean(canAnswer && draft.trim() && draft.trim().length <= draftLimit);
  const selectedFormat = formats.find(format => format.label === creationFormat);
  const formatBadge = useRef<HTMLButtonElement>(null);
  const composerInput = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const badge = formatBadge.current;
    const field = composerInput.current;
    const textarea = input.current;
    if (!field || !textarea) return;
    field.style.setProperty("--prompt-scroll", `${textarea.scrollTop}px`);
    if (!badge) {
      field.style.removeProperty("--prompt-indent");
      return;
    }
    const align = () => field.style.setProperty("--prompt-indent", `${Math.ceil(badge.getBoundingClientRect().width) + 8}px`);
    align();
    const observer = new ResizeObserver(align);
    observer.observe(badge);
    return () => observer.disconnect();
  }, [input, selectedFormat]);
  function selectFormat(label: string | null) {
    setCreationFormat(label);
    input.current?.focus();
  }
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
    </div>
    <ScrollArea.Root className={styles.scrollRoot} type="scroll">
      <ScrollArea.Viewport className={styles.conversation} ref={chatScroll}>
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
            {message.role === "assistant" && (message.timeline?.length || message.billing) ? (
              <CreationTimeline timeline={message.timeline ?? []} billing={message.billing}
                elapsedMs={message.durationMs ?? message.billing?.durationMs}
                learningPlan={message.learningPlan} publicBrief={message.publicBrief} />
            ) : null}
            {message.role === "assistant" ? <>
              {parsed?.body ? <MessageMarkdown content={parsed.body} /> : null}
              {choice && <AgentChoicePrompt choice={choice} disabled={!canAnswer || i !== messages.length - 1}
                onAnswer={(answer, structured) => { void send(answer, structured); }} />}
            </> : message.content}
            {message.rpgEditJobId && /^[0-9a-f]{32}$/.test(message.rpgEditJobId) && <p>
              <a href={withBasePath("/jobs/" + message.rpgEditJobId)}
                target="_blank" rel="noopener noreferrer">
                打开 WebGAL 游戏编辑工作台 <ArrowUpRight size={14} aria-hidden="true" />
              </a>
            </p>}
            {message.rpg && message.id && conversationId && <RpgTaskCard
              key={message.id} conversationId={conversationId} messageId={message.id}
              initial={message.rpg} />}
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
      {busy && <div className={styles.statusDock} role="status" aria-live="polite">
        {activeTask?.timeline?.length
          ? <CreationTimeline timeline={activeTask.timeline}
              elapsedMs={activeTask.elapsed_ms} learningPlan={activeTask.learning_plan}
              publicBrief={activeTask.public_brief}
              briefStreaming={activeTask.public_brief_state === "STREAMING"} active />
          : !streamText ? <div className={styles.statusHint}>
              <WandSparkles className={styles.statusSparkle} size={18} aria-hidden="true" />
              <span>{progress || "正在判断需求并准备执行…"}</span>
              <span className={styles.statusDots} aria-hidden="true"><i /><i /><i /></span>
            </div> : null}
      </div>}
      <div ref={end} />
      </ScrollArea.Viewport>
      <ScrollArea.Scrollbar className={styles.chatScrollbar} orientation="vertical">
        <ScrollArea.Thumb className={styles.chatScrollThumb}/>
      </ScrollArea.Scrollbar>
    </ScrollArea.Root>
    <div className={styles.composerArea}>
      {loginRequired && <p role="status" className={styles.notice}>
        请通过左侧栏的账号入口登录 NarrativeOS，再使用创作助手。
      </p>}
      {error && <p role="alert" className={styles.error}>{error}</p>}
      <form className={styles.composer} onSubmit={event => { event.preventDefault(); void send(); }}>
        <label htmlFor="teaching-prompt" className="sr-only">输入学习问题</label>
        <div className={styles.composerInput} ref={composerInput}>
          {selectedFormat && <div className={styles.selectedFormatLayer}><button ref={formatBadge} type="button" className={styles.selectedFormat} disabled={busy}
            aria-label={`清除创作形式：${selectedFormat.label}`} onClick={() => selectFormat(null)}>
            <selectedFormat.Icon size={14} aria-hidden="true" />{selectedFormat.label}<X size={13} aria-hidden="true" />
          </button></div>}
          <textarea id="teaching-prompt" ref={input} value={draft} onChange={event => setDraft(event.target.value)}
          maxLength={draftLimit} rows={2} placeholder={selectedFormat?.placeholder ?? "发送消息，描述你想学习或制作的互动体验…"}
          onScroll={event => composerInput.current?.style.setProperty("--prompt-scroll", `${event.currentTarget.scrollTop}px`)}
          disabled={busy} onKeyDown={event => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault(); void send();
            }
          }} />
        </div>
        <div className={styles.composerToolbar}>
          <small>{draft.trim().length > draftLimit ? `选中创作形式后，正文限 ${draftLimit} 字符` : "Enter 发送 · Shift + Enter 换行"}</small>
          <div className={styles.creationFormats} role="group" aria-label="选择创作形式（单选）">
            {formats.map(({ label, Icon }) => <button key={label} type="button" disabled={busy}
              aria-pressed={creationFormat === label} onClick={() => selectFormat(creationFormat === label ? null : label)}>
              <Icon size={14} aria-hidden="true" />{label}
            </button>)}
          </div>
          <span className={styles.actions}>
            <Button type="submit" variant="primary" disabled={!canSubmit} busy={busy}>
              {busy ? "处理中" : <>发送 <Send size={15} strokeWidth={1.7} aria-hidden="true" /></>}
            </Button>
          </span>
        </div>
      </form>
    </div>
  </section>;
}

