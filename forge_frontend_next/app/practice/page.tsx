"use client";


import { useEffect, useRef, useState } from "react";

import { Button } from "../../components/ui/button";
import { ConfirmDialog } from "../../components/ui/modal";
import { forgeApi, ApiError } from "../../lib/api-client";
import { workApi, type SavedWork, type PublicationForm, type SharedWork } from "../../lib/work-api";
import WorkShareDialog from "./work-share-dialog";
import WorkPublishDialog from "./work-publish-dialog";
import styles from "./practice.module.css";
import WorkInspector, { type WorkPreviewData } from "./work-inspector";
import GeneratedWorkCard, { type GeneratedWork } from "./generated-work-card";
import MessageMarkdown from "./message-markdown";
import CreationTimeline, { type TimelineEvent } from "./creation-timeline";
import { followBuildTask, type BuildTask, type LearningPlan } from "./live-progress";
import { readPracticeSession, writePracticeSession, clearPracticeSession, type PendingCreation } from "./practice-session";
import PracticeNavigation from "./practice-navigation";
import ResizableWorkspace from "./resizable-workspace";

type Message = { role: "user" | "assistant"; content: string; timeline?: TimelineEvent[]; durationMs?: number; learningPlan?: LearningPlan; publicBrief?: string; work?: GeneratedWork };
type Reply = { id: string; output: string; duration_ms?: number };
const examples = ["把《赤壁赋》做成可以抽背的互动网页。", "生成一个适合初中生操作的串并联电路实验。", "设计一个知识闯关网页，答完题才能进入下一关。"];

export default function PracticePage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loginRequired, setLoginRequired] = useState(false);
  const [loggedIn, setLoggedIn] = useState(false);
  const [sessionUserId, setSessionUserId] = useState<string | null>(null);
  const [sessionReady, setSessionReady] = useState(false);
  const [pendingRun, setPendingRun] = useState<PendingCreation | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [progress, setProgress] = useState("");
  const [activeTask, setActiveTask] = useState<BuildTask | null>(null);
  const [workPreviews, setWorkPreviews] = useState<Record<string, WorkPreviewData>>({});
  const [savingArtifactId, setSavingArtifactId] = useState<string | null>(null);
  const [publishArtifactId, setPublishArtifactId] = useState<string | null>(null);
  const [metadataArtifactId, setMetadataArtifactId] = useState<string | null>(null);
  const [metadataBusy, setMetadataBusy] = useState(false);
  const [metadataError, setMetadataError] = useState("");
  const [revokeArtifactId, setRevokeArtifactId] = useState<string | null>(null);
  const [publicationBusy, setPublicationBusy] = useState(false);
  const [publicationError, setPublicationError] = useState("");
  const [revokeError, setRevokeError] = useState("");
  const [shareData, setShareData] = useState<SharedWork | null>(null);
  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(null);
  const [currentArtifactId, setCurrentArtifactId] = useState<string | null>(null);
  const selectedWork = selectedArtifactId ? workPreviews[selectedArtifactId] : undefined;
  const publishWork = publishArtifactId ? workPreviews[publishArtifactId] : undefined;
  const metadataWork = metadataArtifactId ? workPreviews[metadataArtifactId] : undefined;
  const alive = useRef(true);
  const pending = useRef(false);
  const end = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);

  useEffect(() => {
    let active = true;
    forgeApi<{ auth_type?: string; id?: string }>("/auth/me").then(user => {
      if (active) { setLoggedIn(user.auth_type === "sso"); setLoginRequired(user.auth_type !== "sso"); setSessionUserId(user.auth_type === "sso" && user.id ? String(user.id) : null); }
    }).catch(() => { if (active) setLoginRequired(true); }).finally(() => { if (active) setAuthReady(true); });
    return () => { active = false; };
  }, []);
  useEffect(() => { if (messages.length || busy) end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages, busy]);

  // Restore this tab's authenticated conversation and private artifact references
  // after SSO verification. HTML source is always fetched from owner-checked APIs.
  useEffect(() => {
    if (!authReady) return;
    if (!sessionUserId) { setSessionReady(true); return; }
    const savedId = new URL(window.location.href).searchParams.get("work");
    // Different saved works have independent tab conversations; the work loader below
    // still refreshes the authoritative current version on every deep link visit.
    let mounted = true;
    const snapshot = readPracticeSession(sessionUserId, savedId || "general");
    void (async () => {
      if (!snapshot) { if (mounted) setSessionReady(true); return; }
      const loaded: Record<string, WorkPreviewData> = {};
      for (const record of snapshot.works) {
        if (!mounted) break;
        try {
          const url = record.workId && record.currentVersionId &&
            record.savedArtifactId === record.artifactId
            ? `/works/${record.workId}/assets/${record.currentVersionId}/index.html`
            : `/nar-agent/artifacts/${record.artifactId}/index.html`;
          const blob = await forgeApi.blob(url);
          loaded[record.artifactId] = { ...record, html: await blob.text() };
        } catch { /* Expired temporary sources are not added back to the preview list. */ }
      }
      if (!mounted) return;
      setMessages(snapshot.messages);
      setWorkPreviews(loaded);
      setCurrentArtifactId(snapshot.currentArtifactId && loaded[snapshot.currentArtifactId] ? snapshot.currentArtifactId : null);
      setSelectedArtifactId(snapshot.selectedArtifactId && loaded[snapshot.selectedArtifactId] ? snapshot.selectedArtifactId : null);
      setSessionReady(true);
      if (snapshot.pending) void resumePendingRun(snapshot.pending, loaded);
    })();
    return () => { mounted = false; };
  }, [authReady, sessionUserId]);

  useEffect(() => {
    if (!sessionReady || !sessionUserId) return;
    const { searchParams } = new URL(window.location.href);
    writePracticeSession(sessionUserId, {
      messages,
      works: Object.values(workPreviews).map(record => ({ ...record, html: undefined })),
      currentArtifactId, selectedArtifactId, pending: pendingRun,
    }, searchParams.get("work") || "general");
  }, [sessionReady, sessionUserId, messages, workPreviews, currentArtifactId, selectedArtifactId, pendingRun]);


  useEffect(() => {
    // Deep link from the existing "我的作品" page; no local browser storage required.
    const savedId = new URL(window.location.href).searchParams.get("work");
    if (!savedId || !/^[a-f0-9]{32}$/.test(savedId)) return;
    let active = true;
    workApi.get(savedId).then(async ({ work }) => {
      const version = work.versions.find(v => v.id === work.current_version_id);
      if (!version) return;
      const blob = await workApi.html(work.id, version.id);
      if (!active) return;
      const saved: WorkPreviewData = {
        artifactId: version.artifact_id, html: await blob.text(), title: work.title,
        kind: work.kind, version: version.version_number,
        workId: work.id, savedArtifactId: version.artifact_id,
        currentVersionId: version.id,
        publicationStatus: work.publication_status, publicUrl: work.public_url,
        summary: work.summary, subject: work.subject, grade: work.grade, tags: work.tags,
        coverVariant: work.cover_variant,
        versions: work.versions, latestVersionId: work.current_version_id, isHistorical: false,
      };
      if (!active) return;
      setWorkPreviews(previous => ({ ...previous, [saved.artifactId]: saved }));
      setCurrentArtifactId(saved.artifactId);
      setSelectedArtifactId(saved.artifactId);
    }).catch(err => { if (active) setError(err instanceof Error ? err.message : "作品加载失败"); });
    return () => { active = false; };
  }, []);

  async function saveWork(artifactId: string) {
    const work = workPreviews[artifactId];
    if (!loggedIn || !work || savingArtifactId || (work.workId && work.savedArtifactId === artifactId)) return;
    setSavingArtifactId(artifactId);
    setError("");
    try {
      const saved: SavedWork = work.workId
        ? (await workApi.attachVersion(work.workId, artifactId, work.expectedParentArtifactId || work.savedArtifactId || "")).work
        : (await workApi.save({ artifact_id: artifactId, kind: work.kind, title: work.title })).work;
      const version = saved.versions.find(item => item.id === saved.current_version_id);
      if (!version) throw new Error("作品版本保存失败");
      setWorkPreviews(previous => ({
        ...previous,
        [artifactId]: {
          ...previous[artifactId], workId: saved.id, title: saved.title,
          savedArtifactId: artifactId, currentVersionId: version.id,
          version: version.version_number,
          publicationStatus: saved.publication_status, publicUrl: saved.public_url,
          summary: saved.summary, subject: saved.subject, grade: saved.grade, tags: saved.tags,
          coverVariant: saved.cover_variant,
          versions: saved.versions, latestVersionId: saved.current_version_id, isHistorical: false,
        },
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存作品失败，请重试");
    } finally { setSavingArtifactId(null); }
  }


  async function viewSavedVersion(workId: string, versionId: string) {
    if (busy) return;
    setError("");
    try {
      // Retrieve the current owner-scoped version manifest before switching.
      const { work } = await workApi.get(workId);
      const version = work.versions.find(item => item.id === versionId);
      if (!version) throw new Error("该作品版本已不存在");
      const blob = await workApi.html(workId, versionId);
      const entry: WorkPreviewData = {
        artifactId: version.artifact_id, html: await blob.text(), title: work.title,
        kind: work.kind, version: version.version_number,
        workId: work.id, savedArtifactId: version.artifact_id,
        currentVersionId: version.id, latestVersionId: work.current_version_id,
        versions: work.versions, isHistorical: version.id !== work.current_version_id,
        publicationStatus: work.publication_status, publicUrl: work.public_url,
        summary: work.summary, subject: work.subject, grade: work.grade, tags: work.tags,
        coverVariant: work.cover_variant,
      };
      setWorkPreviews(previous => ({ ...previous, [entry.artifactId]: entry }));
      setSelectedArtifactId(entry.artifactId);
      if (!entry.isHistorical) setCurrentArtifactId(entry.artifactId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "读取历史版本失败");
    }
  }

  async function saveMetadata(payload: PublicationForm) {
    const item = metadataArtifactId ? workPreviews[metadataArtifactId] : undefined;
    if (!item?.workId || metadataBusy) return;
    setMetadataBusy(true); setMetadataError("");
    try {
      const result = await workApi.update(item.workId, payload);
      setWorkPreviews(previous => ({
        ...previous,
        [item.artifactId]: {
          ...previous[item.artifactId], title: result.work.title, summary: result.work.summary,
          subject: result.work.subject, grade: result.work.grade, tags: result.work.tags,
          coverVariant: result.work.cover_variant,
        },
      }));
      setMessages(previous => previous.map(message => message.work?.artifactId === item.artifactId
        ? { ...message, work: { ...message.work, title: result.work.title } } : message));
      setMetadataArtifactId(null);
    } catch (err) {
      setMetadataError(err instanceof Error ? err.message : "作品资料保存失败");
    } finally { setMetadataBusy(false); }
  }

  async function submitPublication(payload: PublicationForm) {
    const item = publishArtifactId ? workPreviews[publishArtifactId] : undefined;
    if (!item || item.kind !== "html" || publicationBusy) return;
    setPublicationBusy(true); setPublicationError(""); setError("");
    try {
      // One publish action handles the underlying save/version step automatically.
      // Never expose an unpublished artifact URL or bypass the explicit publish modal.
      let saved: SavedWork | undefined;
      if (!item.workId) {
        saved = (await workApi.save({
          artifact_id: item.artifactId, kind: item.kind,
          title: payload.title, summary: payload.summary,
        })).work;
      } else if (item.savedArtifactId !== item.artifactId) {
        if (!item.expectedParentArtifactId) throw new Error("旧版信息不完整，请重新打开作品后重试");
        saved = (await workApi.attachVersion(
          item.workId, item.artifactId, item.expectedParentArtifactId,
        )).work;
      }
      const workId = saved?.id || item.workId;
      if (!workId) throw new Error("作品尚未保存，请重试");
      if (saved) {
        const latest = saved.versions.find(version => version.id === saved.current_version_id);
        setWorkPreviews(previous => ({
          ...previous,
          [item.artifactId]: {
            ...previous[item.artifactId], workId,
            savedArtifactId: item.artifactId,
            currentVersionId: latest?.id, version: latest?.version_number || item.version,
            versions: saved.versions, latestVersionId: saved.current_version_id, isHistorical: false,
          },
        }));
      }
      const result = await workApi.publish(workId, payload);
      if (!result.published) throw new Error("教师资源广场尚未确认发布");
      setWorkPreviews(previous => ({
        ...previous,
        [item.artifactId]: {
          ...previous[item.artifactId], workId, title: payload.title,
          publicationStatus: "published", publicUrl: result.public_url,
          summary: payload.summary, subject: payload.subject, grade: payload.grade, tags: payload.tags,
        },
      }));
      setPublishArtifactId(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "发布失败，请重试";
      setError(message);
      setPublicationError(message);
    } finally { setPublicationBusy(false); }
  }

  async function revokePublication() {
    const item = revokeArtifactId ? workPreviews[revokeArtifactId] : undefined;
    if (!item?.workId || publicationBusy) return;
    setPublicationBusy(true); setError("");
    try {
      await workApi.unpublish(item.workId);
      setWorkPreviews(previous => ({
        ...previous,
        [item.artifactId]: { ...previous[item.artifactId], publicationStatus: "unpublished", publicUrl: null },
      }));
      setRevokeArtifactId(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "撤回未完成，请重试";
      setError(message);
      setRevokeError(message);
      // Remote de-indexing can fail after the server has revoked all public reads.
      // Always refresh authoritative publication status to disable stale Share buttons.
      if (item.workId) {
        try {
          const status = await workApi.publication(item.workId);
          setWorkPreviews(previous => ({
            ...previous,
            [item.artifactId]: {
              ...previous[item.artifactId], publicationStatus: status.status,
              publicUrl: status.public_url,
            },
          }));
        } catch { /* Keep the error; the server remains authoritative. */ }
      }
    } finally { setPublicationBusy(false); }
  }

  async function openShare(artifactId: string) {
    const item = workPreviews[artifactId];
    if (!item?.workId || item.publicationStatus !== "published") return;
    setError("");
    try {
      // The server rejects private/unpublished/revoked works, regardless of UI state.
      const result = await workApi.share(item.workId);
      setShareData(result);
    } catch (error) {
      setError(error instanceof Error ? error.message : "当前作品无法分享");
    }
  }

  async function completeGeneratedWork(
    task: BuildTask, prompt: string, mode: "animation" | "html" | "edit",
    parentArtifact: string | null, original?: WorkPreviewData,
  ): Promise<GeneratedWork> {
    if (task.status !== "SUCCEEDED" || !task.artifact_id) {
      throw new Error(task.error || "作品未通过检查，请调整要求后重试。");
    }
    const blob = await forgeApi.blob(`/nar-agent/artifacts/${task.artifact_id}/index.html`);
    const title = original?.title || prompt.split(/[。！？!?\n]/)[0].trim().slice(0, 40) || "互动学习作品";
    const work: WorkPreviewData = {
      artifactId: task.artifact_id, html: await blob.text(), title,
      kind: mode === "animation" ? "animation" : "html",
      version: parentArtifact ? (original?.version || 1) + 1 : 1,
      workId: parentArtifact ? original?.workId : undefined,
      savedArtifactId: parentArtifact ? original?.savedArtifactId : undefined,
      currentVersionId: parentArtifact ? original?.currentVersionId : undefined,
      expectedParentArtifactId: parentArtifact || undefined,
      publicationStatus: parentArtifact ? original?.publicationStatus : "draft",
      summary: parentArtifact ? original?.summary : undefined,
      subject: parentArtifact ? original?.subject : undefined,
      grade: parentArtifact ? original?.grade : undefined,
      tags: parentArtifact ? original?.tags : undefined,
      coverVariant: parentArtifact ? original?.coverVariant : "preview",
      versions: parentArtifact ? original?.versions : undefined,
      latestVersionId: parentArtifact ? original?.latestVersionId : undefined,
      isHistorical: false,
      publicUrl: parentArtifact ? original?.publicUrl : null,
    };
    setWorkPreviews(previous => ({ ...previous, [work.artifactId]: work }));
    setCurrentArtifactId(work.artifactId);
    setSelectedArtifactId(work.artifactId);
    return { artifactId: work.artifactId, kind: work.kind, title, version: work.version };
  }

  async function resumePendingRun(run: PendingCreation, loaded: Record<string, WorkPreviewData>) {
    if (pending.current) return;
    let latest: BuildTask | undefined;
    pending.current = true;
    setBusy(true);
    setPendingRun(run);
    setMessages([...run.originalMessages, { role: "user", content: run.prompt }]);
    try {
      const task = await followBuildTask(
        run.endpoint, run.id, run.startedAt,
        snapshot => { latest = snapshot; setActiveTask(snapshot); },
        () => alive.current,
      );
      const generated = await completeGeneratedWork(
        task, run.prompt, run.mode, run.parentArtifactId || null,
        run.parentArtifactId ? loaded[run.parentArtifactId] : undefined,
      );
      setMessages([...run.originalMessages, { role: "user", content: run.prompt },
        { role: "assistant", content: task.output || "作品已经做好，可以打开预览并继续修改。",
          timeline: task.timeline, durationMs: task.elapsed_ms, learningPlan: task.learning_plan, publicBrief: task.public_brief, work: generated }]);
    } catch (error) {
      setMessages([...run.originalMessages, { role: "user", content: run.prompt },
        { role: "assistant", content: "这次创作未能恢复或完成，你可以再次尝试。",
          timeline: latest?.timeline, durationMs: latest?.elapsed_ms, learningPlan: latest?.learning_plan, publicBrief: latest?.public_brief }]);
      setError(error instanceof Error ? error.message : "任务恢复失败，请重试");
      setDraft(run.prompt);
    } finally {
      pending.current = false; setBusy(false); setActiveTask(null); setPendingRun(null);
    }
  }

  async function send(mode: "chat" | "animation" | "html" | "edit" = "chat") {
    const prompt = draft.trim();
    if (!prompt || pending.current || !loggedIn || !sessionReady) return;
    const history = messages.map(message => ({ role: message.role, content: message.content }));
    const originalMessages = messages;
    let lastTask: BuildTask | undefined;
    let generatedWork: GeneratedWork | undefined;
    if (history.length >= 20 || history.reduce((n, m) => n + m.content.length, prompt.length) > 36000) {
      setError("当前对话较长，请开始新对话后继续。"); return;
    }
    pending.current = true;
    setBusy(true); setError(""); setProgress(mode === "animation" ? "正在设计动画…" : mode === "chat" ? "" : "正在制作互动网页…");
    setMessages([...originalMessages, { role: "user", content: prompt }]); setDraft("");
    try {
      const currentWork = currentArtifactId ? workPreviews[currentArtifactId] : undefined;
      const parentArtifact = mode === "edit" && currentWork?.kind === "html" ? currentWork.artifactId : null;
      const body = JSON.stringify({ prompt, history, ...(parentArtifact ? { parent_artifact_id: parentArtifact } : {}) });
      let reply: Reply;
      if (mode !== "chat") {
        const endpoint = mode === "animation" ? "animations" : "html";
        let task = await forgeApi<BuildTask>(`/nar-agent/${endpoint}`, { method: "POST", headers: { "X-NarAgent-Action": "chat" }, body });
        lastTask = task; setActiveTask(task);
        const started = Date.now();
        if (task.status === "RUNNING") setPendingRun({
          id: task.id, endpoint, mode, prompt, parentArtifactId: parentArtifact,
          originalMessages, startedAt: started,
        });
        if (task.status === "RUNNING") {
          task = await followBuildTask(
            endpoint, task.id, started,
            snapshot => { lastTask = snapshot; setActiveTask(snapshot); },
            () => alive.current,
          );
        }
        generatedWork = await completeGeneratedWork(task, prompt, mode, parentArtifact, currentWork);
        reply = { id: task.id, output: task.output || "作品已经做好，可以打开预览并继续修改。" };
      } else reply = await forgeApi<Reply>("/nar-agent/chat", {
        method: "POST", headers: { "X-NarAgent-Action": "chat" }, body: JSON.stringify({ prompt, history }),
      });
      setMessages([...originalMessages, { role: "user", content: prompt }, {
        role: "assistant", content: reply.output, timeline: lastTask?.timeline,
        durationMs: lastTask?.elapsed_ms, learningPlan: lastTask?.learning_plan, publicBrief: lastTask?.public_brief, work: generatedWork,
      }]);
    } catch (cause) {
      if (mode === "chat") setMessages(originalMessages);
      else setMessages([...originalMessages, { role: "user", content: prompt }, { role: "assistant", content: "本次作品没有完成。你可以调整需求后再次尝试。", timeline: lastTask?.timeline, durationMs: lastTask?.elapsed_ms, learningPlan: lastTask?.learning_plan, publicBrief: lastTask?.public_brief }]);
      setDraft(prompt);
      if (cause instanceof ApiError && cause.status === 401) { setLoginRequired(true); setLoggedIn(false); }
      setError(cause instanceof Error ? cause.message : "发送失败，请稍后重试。");
    } finally { pending.current = false; setBusy(false); setActiveTask(null); setPendingRun(null); setProgress(""); input.current?.focus(); }
  }

  function savedCardWorkId(work: GeneratedWork): string | undefined {
    const preview = workPreviews[work.artifactId];
    return preview?.savedArtifactId === work.artifactId ? preview.workId : undefined;
  }

  function beginNewConversation() {
    if (busy) return;
    setMessages([]); setWorkPreviews({}); setPendingRun(null);
    setDraft(""); setError(""); setSelectedArtifactId(null);
    setCurrentArtifactId(null);
    if (sessionUserId) clearPracticeSession(sessionUserId,
      new URL(window.location.href).searchParams.get("work") || "general");
    window.history.replaceState(window.history.state, "", window.location.pathname);
    input.current?.focus();
  }

  const savedWorkCount = Object.values(workPreviews).filter(work => Boolean(work.workId)).length;

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
