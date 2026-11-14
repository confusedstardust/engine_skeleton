"use client";

import { useEffect, useRef, useState } from "react";
import { forgeApi, ApiError } from "../../lib/api-client";
import { loadSavedWork } from "./practice-work-service";
import type { WorkPreviewData } from "./work-inspector";
import type { GeneratedWork } from "./generated-work-card";
import { followBuildTask, type BuildTask } from "./live-progress";
import { readPracticeSession, writePracticeSession, clearPracticeSession, type PendingCreation } from "./practice-session";
import { usePracticeLibrary } from "./use-practice-library";
import type { PracticeMessage, ChatReply } from "./practice-types";

export function usePracticeWorkspace() {
  const [messages, setMessages] = useState<PracticeMessage[]>([]);
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
  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(null);
  const [currentArtifactId, setCurrentArtifactId] = useState<string | null>(null);
  const library = usePracticeLibrary({
    workPreviews, setWorkPreviews, setMessages, loggedIn, busy, setError,
    setSelectedArtifactId, setCurrentArtifactId,
  });
  const { publishArtifactId, metadataArtifactId } = library;
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
    loadSavedWork(savedId).then(saved => {
      if (!active) return;
      setWorkPreviews(previous => ({ ...previous, [saved.artifactId]: saved }));
      setCurrentArtifactId(saved.artifactId);
      setSelectedArtifactId(saved.artifactId);
    }).catch(err => { if (active) setError(err instanceof Error ? err.message : "作品加载失败"); });
    return () => { active = false; };
  }, []);

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
      let reply: ChatReply;
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
      } else reply = await forgeApi<ChatReply>("/nar-agent/chat", {
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

  return {
    messages, draft, setDraft, busy, error, loginRequired, loggedIn, sessionUserId,
    sessionReady, authReady, progress, activeTask, workPreviews, selectedWork, publishWork,
    metadataWork, selectedArtifactId, setSelectedArtifactId, currentArtifactId, setCurrentArtifactId,
    end, input, savedWorkCount, send, beginNewConversation, savedCardWorkId,
    ...library,
  };


}
