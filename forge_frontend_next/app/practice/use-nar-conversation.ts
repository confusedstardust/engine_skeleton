"use client";

import { useCallback, useEffect, useRef, useState, type Dispatch, type RefObject, type SetStateAction } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { conversationApi, type ConversationArtifact, type ServerTurn, type ConversationDetail } from "../../lib/conversation-api";
import { workApi } from "../../lib/work-api";
import { previewConversationArtifact, messagesFromConversation } from "./practice-conversation";
import type { PracticeMessage } from "./practice-types";
import type { WorkPreviewData } from "./work-inspector";
import type { BuildTask } from "./live-progress";

type Args = {
  conversationId?: string;
  authReady: boolean;
  loggedIn: boolean;
  setSessionReady: Dispatch<SetStateAction<boolean>>;
  setMessages: Dispatch<SetStateAction<PracticeMessage[]>>;
  setWorkPreviews: Dispatch<SetStateAction<Record<string, WorkPreviewData>>>;
  setSelectedArtifactId: Dispatch<SetStateAction<string | null>>;
  setCurrentArtifactId: Dispatch<SetStateAction<string | null>>;
  setBusy: Dispatch<SetStateAction<boolean>>;
  setActiveTask: Dispatch<SetStateAction<BuildTask | null>>;
  setError: Dispatch<SetStateAction<string>>;
  setDraft: Dispatch<SetStateAction<string>>;
  setProgress: Dispatch<SetStateAction<string>>;
  input: RefObject<HTMLTextAreaElement | null>;
};

function uuid(): string {
  // The development workbench also runs on HTTP. randomUUID() requires a
  // secure context; getRandomValues() does not.
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  return Array.from(bytes, value => value.toString(16).padStart(2, "0")).join("");
}

function terminal(status: string): boolean {
  return status === "SUCCEEDED" || status === "FAILED" || status === "UNKNOWN";
}

/** Durable history does not reuse the per-tab cache. All history reads are
 * owner checked by Forge and body HTML is fetched only on explicit preview. */
export function useNarConversation({
  conversationId, authReady, loggedIn, setSessionReady, setMessages,
  setWorkPreviews, setSelectedArtifactId, setCurrentArtifactId,
  setBusy, setActiveTask, setError, setDraft, setProgress, input,
}: Args) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedArtifact = searchParams.get("artifact");
  const [enabled, setEnabled] = useState(false);
  const [checked, setChecked] = useState(false);
  const [artifacts, setArtifacts] = useState<ConversationArtifact[]>([]);
  const [activeTurn, setActiveTurn] = useState<ServerTurn | null>(null);
  const [olderCursor, setOlderCursor] = useState<number | null>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [revision, setRevision] = useState(0);
  const [conversationTitle, setConversationTitle] = useState("");
  const inFlight = useRef<{ cid: string; requestId: string; prompt: string; mode: string } | null>(null);
  const alive = useRef(true);
  const chatScroll = useRef<HTMLDivElement>(null);
  const skipScroll = useRef(false);

  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);

  useEffect(() => {
    if (!authReady) return;
    let active = true;
    setChecked(false);
    if (!loggedIn) { setEnabled(false); setChecked(true); return; }
    void conversationApi.status().then(r => {
      if (active) setEnabled(r.enabled);
    }).catch(() => { if (active) setEnabled(false); })
      .finally(() => { if (active) setChecked(true); });
    return () => { active = false; };
  }, [authReady, loggedIn]);

  const applyDetail = useCallback((detail: ConversationDetail) => {
    if (!alive.current) return;
    setMessages(messagesFromConversation(detail));
    setArtifacts(detail.artifacts);
    setConversationTitle(detail.conversation.title);
    setOlderCursor(detail.nextBefore);
    setActiveTurn(detail.activeTurn);
    setRevision(v => v + 1);
  }, [setMessages]);

  useEffect(() => {
    if (!conversationId || !authReady || !checked) return;
    if (!loggedIn || !enabled) {
      setSessionReady(true);
      setError("跨设备会话功能尚未启用，请先由管理员迁移数据库并开启该功能。");
      return;
    }
    let active = true;
    setSessionReady(false);
    void conversationApi.get(conversationId).then(detail => {
      if (active) { applyDetail(detail); setSessionReady(true); }
    }).catch(e => {
      if (active) { setError(e instanceof Error ? e.message : "会话加载失败"); setSessionReady(true); }
    });
    return () => { active = false; };
  }, [conversationId, authReady, checked, loggedIn, enabled, applyDetail, setError, setSessionReady]);

  const openArtifact = useCallback(async (id: string) => {
    const target = artifacts.find(item => item.artifactId === id);
    if (!target) return;
    try {
      const preview = await previewConversationArtifact(target);
      if (!alive.current) return;
      setWorkPreviews(previous => ({ ...previous, [preview.artifactId]: preview }));
      setCurrentArtifactId(preview.artifactId);
      setSelectedArtifactId(preview.artifactId);
    } catch (error) {
      if (alive.current) setError(error instanceof Error ? error.message : "历史作品预览已过期");
    }
  }, [artifacts, setWorkPreviews, setSelectedArtifactId, setCurrentArtifactId, setError]);

  useEffect(() => {
    if (!conversationId || !requestedArtifact || !/^[a-f0-9]{32}$/.test(requestedArtifact)) return;
    if (!artifacts.some(item => item.artifactId === requestedArtifact)) return;
    void openArtifact(requestedArtifact);
  }, [conversationId, requestedArtifact, artifacts, openArtifact]);

  // Query a running turn while this conversation is visible. Switching routes
  // cancels the loop. A QUEUED/UNKNOWN dispatch is never blindly retried.
  useEffect(() => {
    if (!conversationId || !enabled || !activeTurn) return;
    if (terminal(activeTurn.status)) {
      setBusy(false);
      if (activeTurn.status === "UNKNOWN") {
        setError("这次任务的执行结果尚未确认，请不要重复提交。请检查执行服务状态。");
      }
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let attempts = 0;
    setBusy(true);
    const poll = async () => {
      if (cancelled) return;
      try {
        const response = await conversationApi.turnStatus(conversationId, activeTurn.id);
        if (cancelled) return;
        const turn = response.turn;
        if (response.task) setActiveTask(response.task as unknown as BuildTask);
        if (terminal(turn.status)) {
          setBusy(false); setActiveTask(null);
          // Keep the poll effect alive until the final persisted session detail
          // is refreshed. Clearing activeTurn early cancels this very effect.
          if (turn.status !== "SUCCEEDED") {
            setError(turn.status === "UNKNOWN"
              ? "上次任务是否已执行无法确认，请勿重复提交。可能需要人工检查服务状态。"
              : "上次创作未完成，可修改需求后重新发送。");
          } else {
            // Persist newly generated artifacts in the existing owner-scoped
            // work library before showing them as long-term history.
            const artId = response.task?.artifact_id;
            if (typeof artId === "string" && /^[a-f0-9]{32}$/.test(artId)) {
              try {
                let savedWorkId: string | undefined;
                if (turn.mode === "edit" && turn.parentArtifactId) {
                  const { works } = await workApi.list();
                  const alreadySaved = works.find(work =>
                    work.versions.some(version => version.artifact_id === artId));
                  const parentWork = works.find(work =>
                    work.versions.some(version => version.artifact_id === turn.parentArtifactId));
                  if (alreadySaved) {
                    savedWorkId = alreadySaved.id;
                  } else if (parentWork) {
                    const current = parentWork.versions.find(
                      version => version.id === parentWork.current_version_id);
                    if (current?.artifact_id !== turn.parentArtifactId) {
                      throw new Error("作品版本已变化，无法自动追加到旧版本");
                    }
                    const updated = await workApi.attachVersion(
                      parentWork.id, artId, turn.parentArtifactId);
                    savedWorkId = updated.work.id;
                  }
                }
                if (!savedWorkId) {
                  const saved = await workApi.save({
                    artifact_id: artId,
                    kind: turn.mode === "animation" ? "animation" : "html",
                    title: conversationTitle || "互动学习作品",
                  });
                  savedWorkId = saved.work.id;
                }
                await conversationApi.associateWork(conversationId, artId, savedWorkId);
              } catch {
                // Never turn a successfully completed run into a failed turn.
                // The generated artifact link may remain ephemeral until saved.
                setError("作品已生成，但长期保存未完成。请打开作品后手动保存。");
              }
            }
          }
          if (!cancelled) {
            const detail = await conversationApi.get(conversationId);
            if (!cancelled) applyDetail(detail);
          }
          return;
        }
        if (turn.status === "QUEUED" && ++attempts > 8) {
          setError("会话已记录请求，但尚未确认执行。请勿重复提交，避免重复生成。");
          setBusy(false);
          return;
        }
      } catch {
        if (!cancelled) setError("查询生成进度暂时失败，稍后可通过同一会话重新查看。");
      }
      if (!cancelled) timer = setTimeout(() => { void poll(); }, 1800);
    };
    void poll();
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
  }, [conversationId, enabled, activeTurn?.id, activeTurn?.status, applyDetail,
      setBusy, setActiveTask, setError, conversationTitle]);

  async function send(prompt: string, mode: "chat" | "html" | "animation" | "edit",
                      parentArtifact?: string): Promise<boolean> {
    if (!enabled || !checked || !loggedIn) return false;
    const last = inFlight.current;
    const targetId = last?.prompt === prompt && last.mode === mode ? last.cid : conversationId || uuid();
    const requestId = last?.prompt === prompt && last.mode === mode ? last.requestId : uuid();
    inFlight.current = { cid: targetId, requestId, prompt, mode };
    setBusy(true); setError("");
    setProgress(mode === "chat" ? "正在回复…" : "正在生成学习作品…");
    setDraft("");
    try {
      const result = conversationId
        ? await conversationApi.turn(targetId, requestId, prompt, mode, parentArtifact)
        : await conversationApi.create(targetId, requestId, prompt, mode, parentArtifact);
      inFlight.current = null;
      if (!conversationId) {
        router.push("/practice/chat/" + targetId);
      } else {
        const detail = await conversationApi.get(targetId);
        applyDetail(detail);
        if (!detail.activeTurn) setBusy(false);
      }
      if (terminal(result.turn.status) && result.turn.status !== "SUCCEEDED")
        setError("提交状态未能确认，请勿立即重试。请查看当前会话记录。");
    } catch (e) {
      // Keep the same idempotency key if the POST may have reached the server.
      setDraft(prompt);
      setError(e instanceof Error ? e.message : "提交失败，重试会复用相同的请求标识。");
      setBusy(false);
    } finally {
      setProgress("");
      input.current?.focus();
    }
    return true;
  }

  async function loadOlder() {
    if (!conversationId || olderCursor == null || loadingOlder || !enabled) return;
    setLoadingOlder(true);
    const node = chatScroll.current;
    const previousHeight = node?.scrollHeight ?? 0;
    skipScroll.current = true;
    try {
      const page = await conversationApi.messages(conversationId, olderCursor);
      if (!alive.current) return;
      // Do not duplicate messages whose sequence range overlaps a refresh.
      const older = page.items.map(item => ({
        id: item.id, seq: item.seq, role: item.role, content: item.content,
        publicBrief: item.metadata?.publicBrief,
        timeline: item.metadata?.timeline as PracticeMessage["timeline"],
        learningPlan: item.metadata?.learningPlan as PracticeMessage["learningPlan"],
        durationMs: item.metadata?.elapsedMs,
        ...(artifacts.find(a => a.originMessageId === item.id)
          ? { work: (() => {
            const a = artifacts.find(a => a.originMessageId === item.id)!;
            return { artifactId: a.artifactId, title: a.title, kind: a.kind, version: 1 };
          })() } : {}),
      } as PracticeMessage));
      setMessages(current => {
        const known = new Set(current.map(m => m.id).filter(Boolean));
        return [...older.filter(item => !known.has(item.id)), ...current];
      });
      setOlderCursor(page.nextBefore);
      requestAnimationFrame(() => {
        if (node) node.scrollTop += node.scrollHeight - previousHeight;
        skipScroll.current = false;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载更早消息失败");
      skipScroll.current = false;
    } finally { setLoadingOlder(false); }
  }

  return {
    enabled, checked, revision, conversationId, conversationTitle, artifacts,
    activeTurn, olderCursor, loadingOlder, loadOlder, chatScroll, skipScroll,
    openArtifact, send, refresh: async () => {
      if (!conversationId || !enabled) return;
      applyDetail(await conversationApi.get(conversationId));
    },
  };
}
