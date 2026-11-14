"use client";

import { Button } from "../../components/ui/button";
import { ConfirmDialog } from "../../components/ui/modal";
import WorkShareDialog from "./work-share-dialog";
import WorkPublishDialog from "./work-publish-dialog";
import WorkInspector from "./work-inspector";
import GeneratedWorkCard from "./generated-work-card";
import MessageMarkdown from "./message-markdown";
import CreationTimeline from "./creation-timeline";
import PracticeNavigation from "./practice-navigation";
import ResizableWorkspace from "./resizable-workspace";
import { usePracticeWorkspace } from "./use-practice-workspace";
import styles from "./practice.module.css";

const examples = ["把《赤壁赋》做成可以抽背的互动网页。", "生成一个适合初中生操作的串并联电路实验。", "设计一个知识闯关网页，答完题才能进入下一关。"];

export default function PracticePage() {
  const {
    messages, draft, setDraft, busy, error, loginRequired, loggedIn, sessionUserId,
    sessionReady, authReady, progress, activeTask, workPreviews, selectedWork, publishWork,
    metadataWork, setSelectedArtifactId, currentArtifactId, setCurrentArtifactId,
    end, input, savedWorkCount, send, beginNewConversation, savedCardWorkId,
    savingArtifactId, setPublishArtifactId, setMetadataArtifactId, metadataBusy, metadataError, setMetadataError,
    setRevokeArtifactId, publicationBusy, publicationError, setPublicationError,
    revokeArtifactId, revokeError, setRevokeError, shareData, setShareData,
    saveWork, viewSavedVersion, saveMetadata, submitPublication, revokePublication, openShare,
  } = usePracticeWorkspace();
  return <main className={styles.page}>
    <header className={styles.header}><span className={styles.headerTitle}>互动学习创作 <span>／ 工作台</span></span></header>
    <ResizableWorkspace userId={sessionUserId}
      navigation={({ collapsed, onToggle }) => <PracticeNavigation loggedIn={loggedIn} busy={busy}
        refreshKey={savedWorkCount} collapsed={collapsed} onToggle={onToggle}
        onNewConversation={beginNewConversation} />}
      chat={<section className={styles.chat} aria-label="NarrativeOS 互动学习创作助手">
        <div className={styles.chatHeader}><div><strong>互动学习创作</strong><span>用自然语言制作可操作、可修改的教学网页。</span></div><span className={styles.badge}>方案对话</span></div>
        <div className={styles.conversation}>
          {messages.length === 0 && <div className={styles.empty}><span className={styles.spark} aria-hidden="true">✦</span><p className={styles.eyebrow}>从一个课堂问题开始</p><h2>你想制作什么<br />互动学习体验？</h2><p>描述学科、年级、玩法或参考模板。可以生成练习卡、实验模拟与互动学习网页。</p><div className={styles.examples}>{examples.map((example, i) => <button key={example} type="button" onClick={() => { setDraft(example); input.current?.focus(); }}><span>0{i + 1}</span>{example}<b aria-hidden="true">↗</b></button>)}</div></div>}
          {messages.map((message, i) => <article key={i} className={`${styles.message} ${message.role === "user" ? styles.user : styles.assistant}`}><span className={styles.speaker}>{message.role === "user" ? "你" : "教学助手"}</span><div>{message.timeline?.length ? <CreationTimeline timeline={message.timeline} elapsedMs={message.durationMs} learningPlan={message.learningPlan} publicBrief={message.publicBrief} /> : null}{message.role === "assistant" ? <MessageMarkdown content={message.content} /> : message.content}
              {message.work && <GeneratedWorkCard work={message.work} savedWorkId={savedCardWorkId(message.work)} onOpen={id => { setSelectedArtifactId(id); setCurrentArtifactId(id); }} />}
            </div></article>)}
          {busy && (activeTask?.timeline?.length ? <CreationTimeline timeline={activeTask.timeline} elapsedMs={activeTask.elapsed_ms} learningPlan={activeTask.learning_plan} publicBrief={activeTask.public_brief} briefStreaming={activeTask.public_brief_state === "STREAMING"} active /> : <p role="status" className={styles.thinking}>{progress || "正在理解学习需求…"}</p>)}
          <div ref={end} />
        </div>
        <div className={styles.composerArea}>
          {loginRequired && <p role="status" className={styles.notice}>请通过右上角账号菜单登录 NarrativeOS，再使用讲练助手。登录后可刷新页面。</p>}
          {error && <p role="alert" className={styles.error}>{error}</p>}
          <form className={styles.composer} onSubmit={event => { event.preventDefault(); void send(); }}>
            <label htmlFor="teaching-prompt" className="sr-only">输入教学问题</label>
            <textarea id="teaching-prompt" ref={input} value={draft} onChange={event => setDraft(event.target.value)} maxLength={12000} rows={3} placeholder="例如：用串联电路讲解电流，学生可以点击开关…" disabled={busy} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(); } }} />
            <div><small>Enter 发送 · Shift + Enter 换行</small><span className={styles.actions}><Button onClick={() => { void send("animation"); }} disabled={busy || !authReady || !sessionReady || !loggedIn || !draft.trim()}>制作动画</Button><Button onClick={() => { void send("html"); }} disabled={busy || !authReady || !sessionReady || !loggedIn || !draft.trim()}>生成 HTML</Button>{currentArtifactId && workPreviews[currentArtifactId]?.kind === "html" && <Button onClick={() => { void send("edit"); }} disabled={busy || !authReady || !sessionReady || !loggedIn || !draft.trim()}>修改当前作品</Button>}<Button type="submit" variant="primary" disabled={!authReady || !sessionReady || !loggedIn || !draft.trim()} busy={busy}>{busy ? "处理中" : "发送 ↗"}</Button></span></div>
          </form>
          <p className={styles.disclaimer}>生成内容用于备课参考，课堂使用前请核对知识与参数。</p>
        </div>
      </section>}
      inspector={selectedWork ? <WorkInspector work={selectedWork}
        onClose={() => setSelectedArtifactId(null)}
        onEdit={id => { setCurrentArtifactId(id); input.current?.focus(); }}
        onSave={id => { void saveWork(id); }} saving={savingArtifactId === selectedWork.artifactId}
        onEditMetadata={id => { setMetadataError(""); setMetadataArtifactId(id); }}
        onViewVersion={(workId, versionId) => { void viewSavedVersion(workId, versionId); }}
        onPublish={id => { setPublicationError(""); setPublishArtifactId(id); }}
        onUnpublish={id => { setRevokeError(""); setRevokeArtifactId(id); }}
        onShare={id => { void openShare(id); }}
        publishing={publicationBusy} /> : undefined} />
    {metadataWork && <WorkPublishDialog key={"metadata:" + metadataWork.artifactId}
      mode="edit" work={metadataWork} onClose={() => setMetadataArtifactId(null)}
      busy={metadataBusy} error={metadataError}
      onSubmit={payload => { void saveMetadata(payload); }} />}
    {shareData && <WorkShareDialog data={shareData} onClose={() => setShareData(null)} />}
    {publishWork && <WorkPublishDialog key={publishWork.artifactId} work={publishWork}
      onClose={() => setPublishArtifactId(null)} busy={publicationBusy} error={publicationError}
      onSubmit={payload => { void submitPublication(payload); }} />}
    <ConfirmDialog open={Boolean(revokeArtifactId)} error={revokeError} title="撤回教师广场发布"
      description="撤回后，已有公开链接也将无法继续访问作品。私有作品与版本记录会保留。"
      busy={publicationBusy} onCancel={() => setRevokeArtifactId(null)}
      onConfirm={() => { void revokePublication(); }} />
  </main>;
}
