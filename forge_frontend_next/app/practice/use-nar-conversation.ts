"use client";

import { useCallback, useEffect, useRef, useState, type Dispatch, type RefObject, type SetStateAction } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { conversationApi, type ConversationArtifact, type ServerTurn, type ConversationDetail } from "../../lib/conversation-api";
import { workApi } from "../../lib/work-api";
import {
  CONVERSATION_STALE_MS, getConversationQuery, peekConversationQuery,
  setConversationQuery, upsertConversationSummary, invalidateConversationQuery,
  subscribeConversationQuery,
} from "../../lib/conversation-query-cache";
import { previewConversationArtifact, messagesFromConversation } from "./practice-conversation";
import type { PracticeMessage } from "./practice-types";
import type { WorkPreviewData } from "./work-inspector";
import type { BuildTask } from "./live-progress";
import { formatPracticeFailure } from "./practice-failure";

type Args = {
  conversationId?: string;
  authReady: boolean;
  loggedIn: boolean;
  ownerId: string | null;
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
  conversationId, authReady, loggedIn, ownerId, setSessionReady, setMessages,
  setWorkPreviews, setSelectedArtifactId, setCurrentArtifactId,
  setBusy, setActiveTask, setError, setDraft, setProgress, input,
}: Args) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedArtifact = searchParams.get("artifact");
  const [ready, setReady] = useState(false);
  const [checked, setChecked] = useState(false);
  const [artifacts, setArtifacts] = useState<ConversationArtifact[]>([]);
  const [activeTurn, setActiveTurn] = useState<ServerTurn | null>(null);
  const [olderCursor, setOlderCursor] = useState<number | null>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [conversationTitle, setConversationTitle] = useState("");
  const inFlight = useRef<{ cid: string; requestId: string; prompt: string; mode: string; parentArtifact?: string } | null>(null);
  const posting = useRef(false);
  const alive = useRef(true);
  const previewRequest = useRef(0);
  const previousConversation = useRef<string | undefined>(conversationId);
  const currentConversation = useRef<string | undefined>(conversationId);
  currentConversation.current = conversationId;
  const chatScroll = useRef<HTMLDivElement>(null);
  const skipScroll = useRef(false);

  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);

  useEffect(() => {
    if (!authReady) return;
    let active = true;
    setChecked(false);
    if (!loggedIn || !ownerId) { setReady(false); setChecked(true); return; }
    // Readiness is an authenticated server query, cached for 5 minutes.
    // Never re-check the entire schema on every conversation page mount.
    void getConversationQuery(ownerId, "readiness", CONVERSATION_STALE_MS.readiness,
      () => conversationApi.status()).then(r => {
      if (active) setReady(r.ready);
    }).catch(error => {
      if (active) {
        setReady(false);
        setError(error instanceof Error ? error.message :
          "会话数据库不可用，请先执行 002_nar_conversation_history.sql");
      }
    }).finally(() => { if (active) setChecked(true); });
    return () => { active = false; };
  }, [authReady, loggedIn, ownerId, setError]);

  // Route changes update only the active pane. Navigation/header/sidebar stay
  // mounted in practice/layout.tsx; never leak work A's private state into B.
  useEffect(() => {
    if (previousConversation.current === conversationId) return;
    previousConversation.current = conversationId;
    previewRequest.current++;
    setMessages([]); setWorkPreviews({});
    setSelectedArtifactId(null); setCurrentArtifactId(null);
    setActiveTurn(null); setActiveTask(null);
    setArtifacts([]); setOlderCursor(null);
    setConversationTitle(""); setError(""); setDraft("");
    setBusy(false); setProgress("");
    setSessionReady(false);
  }, [conversationId, setMessages, setWorkPreviews, setSelectedArtifactId,
      setCurrentArtifactId, setActiveTask, setError, setDraft, setBusy,
      setProgress, setSessionReady]);

  // Rename and pin updates from the sidebar should update the open conversation header.
  useEffect(() => {
    if (!ownerId || !conversationId) return;
    return subscribeConversationQuery(ownerId, "detail:" + conversationId, () => {
      const detail = peekConversationQuery<ConversationDetail>(ownerId, "detail:" + conversationId);
      if (detail && alive.current) setConversationTitle(detail.conversation.title);
    });
  }, [ownerId, conversationId]);

  const applyDetail = useCallback((detail: ConversationDetail) => {
    if (!alive.current) return;
    setMessages(messagesFromConversation(detail));
    setArtifacts(detail.artifacts);
    setConversationTitle(detail.conversation.title);
    setOlderCursor(detail.nextBefore);
    setActiveTurn(detail.activeTurn);
  }, [setMessages]);

  useEffect(() => {
    if (!conversationId || !authReady || !checked) return;
    if (!loggedIn || !ready) {
      setSessionReady(true);
      if (loggedIn) setError("会话数据库尚未准备好，请先执行 002_nar_conversation_history.sql");
      return;
    }
    if (!ownerId) return;
    let active = true;
    const key = "detail:" + conversationId;
    const cached = peekConversationQuery<ConversationDetail>(ownerId, key);
    if (cached) {
      // Stale-while-revalidate: paint the prior conversation instantly, no blank
      // chat, spinner or global sidebar refresh on back/forward navigation.
      applyDetail(cached);
      setSessionReady(true);
    } else {
      setSessionReady(false);
    }
    void getConversationQuery(ownerId, key, CONVERSATION_STALE_MS.detail,
      () => conversationApi.get(conversationId)).then(detail => {
      if (active && (!cached || cached !== detail)) applyDetail(detail);
      if (active) setSessionReady(true);
    }).catch(e => {
      if (active) {
        if (!cached) setError(e instanceof Error ? e.message : "会话加载失败");
        setSessionReady(true);
      }
    });
    return () => { active = false; };
  }, [conversationId, authReady, checked, loggedIn, ready, ownerId, applyDetail, setError, setSessionReady]);

  const openArtifact = useCallback(async (id: string) => {
    const target = artifacts.find(item => item.artifactId === id);
    if (!target) return;
    // A slower old preview must never replace a later click in the same chat.
    const requestId = ++previewRequest.current;
    try {
      const preview = ownerId
        ? await getConversationQuery(ownerId, "preview:" + id, 10 * 60_000,
            () => previewConversationArtifact(target))
        : await previewConversationArtifact(target);
      if (!alive.current || requestId !== previewRequest.current) return;
      setWorkPreviews(previous => ({ ...previous, [preview.artifactId]: preview }));
      setCurrentArtifactId(preview.artifactId);
      setSelectedArtifactId(preview.artifactId);
    } catch (error) {
      if (alive.current && requestId === previewRequest.current) setError(error instanceof Error ? error.message : "历史作品预览已过期");
    }
  }, [artifacts, ownerId, setWorkPreviews, setSelectedArtifactId, setCurrentArtifactId, setError]);

  useEffect(() => {
    if (!conversationId || !requestedArtifact || !/^[a-f0-9]{32}$/.test(requestedArtifact)) return;
    if (!artifacts.some(item => item.artifactId === requestedArtifact)) return;
    void openArtifact(requestedArtifact);
  }, [conversationId, requestedArtifact, artifacts, openArtifact]);

  const activeTurnId = activeTurn?.id;
  const activeTurnStatus = activeTurn?.status;

  // Query a running turn while this conversation is visible. Switching routes
  // cancels the loop. A QUEUED/UNKNOWN dispatch is never blindly retried.
  useEffect(() => {
    if (!conversationId || !ready || !activeTurnId || !ownerId) return;
    if (activeTurnStatus && terminal(activeTurnStatus)) {
      setBusy(false);
      if (activeTurnStatus === "UNKNOWN") {
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
        const response = await conversationApi.turnStatus(conversationId, activeTurnId);
        if (cancelled) return;
        const turn = response.turn;
        if (response.task) setActiveTask(response.task as unknown as BuildTask);
        if (terminal(turn.status)) {
          setBusy(false); setActiveTask(null);
          // Keep the poll effect alive until the final persisted session detail
          // is refreshed. Clearing activeTurn early cancels this very effect.
          if (turn.status !== "SUCCEEDED") {
            setError(formatPracticeFailure(turn, response.task));
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
            const detail = await getConversationQuery(ownerId, "detail:" + conversationId, 0,
              () => conversationApi.get(conversationId), { force: true });
            if (!cancelled) {
              applyDetail(detail);
              upsertConversationSummary(ownerId, detail.conversation);
              if (turn.status === "SUCCEEDED") invalidateConversationQuery(ownerId, "artifacts");
            }
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
  }, [conversationId, ready, ownerId, activeTurnId, activeTurnStatus, applyDetail,
      setBusy, setActiveTask, setError, conversationTitle]);

  async function send(prompt: string, mode: "auto" | "chat" | "html" | "animation" | "edit",
                      parentArtifact?: string): Promise<boolean> {
    if (!ready || !checked || !loggedIn || posting.current) return false;
    posting.current = true;
    const last = inFlight.current;
    const retry = last?.prompt === prompt && last.mode === mode && last.parentArtifact === parentArtifact;
    const targetId = retry ? last.cid : conversationId || uuid();
    const requestId = retry ? last.requestId : uuid();
    inFlight.current = { cid: targetId, requestId, prompt, mode, parentArtifact };
    setBusy(true); setError("");
    setProgress(mode === "auto" ? "正在理解学习需求…" : mode === "chat" ? "正在回复…" : "正在生成学习作品…");
    // Optimistic paint must happen before the HTTP request (chat dispatch can take minutes).
    // Reconciliation replaces this temporary ID with server-owned message IDs.
    setMessages(current => current.some(message => message.id === requestId)
      ? current : [...current, { id: requestId, role: "user", content: prompt }]);
    setDraft("");
    try {
      const result = conversationId
        ? await conversationApi.turn(targetId, requestId, prompt, mode, parentArtifact)
        : await conversationApi.create(targetId, requestId, prompt, mode, parentArtifact);
      inFlight.current = null;
      // Server request may complete after user clicked another conversation.
      // Keep its DB changes, but never navigate/apply obsolete UI state.
      if (currentConversation.current !== conversationId) return true;
      if (!conversationId) {
        // Prepare a minimal server-accepted snapshot for instant navigation.
        // The new route revalidates only this conversation in the background.
        if (ownerId) {
          const now = new Date().toISOString();
          setConversationQuery<ConversationDetail>(ownerId, "detail:" + targetId, {
            conversation: { id: targetId, title: prompt.slice(0, 160),
              createdAt: now, activeAt: now },
            messages: [{ id: requestId, seq: 1, role: "user",
              content: prompt, createdAt: now }],
            nextBefore: null,
            activeTurn: result.turn.status === "RUNNING" || result.turn.status === "QUEUED"
              || result.turn.status === "UNKNOWN" ? result.turn : null,
            artifacts: [],
          });
          invalidateConversationQuery(ownerId, "detail:" + targetId);
          upsertConversationSummary(ownerId, { id: targetId, title: prompt.slice(0, 160) });
        }
        router.push("/practice/chat/" + targetId);
      } else {
        const detail = await getConversationQuery(ownerId!, "detail:" + targetId, 0,
          () => conversationApi.get(targetId), { force: true });
        applyDetail(detail);
        upsertConversationSummary(ownerId!, detail.conversation);
        if (!detail.activeTurn) setBusy(false);
      }
      if (terminal(result.turn.status) && result.turn.status !== "SUCCEEDED")
        setError(formatPracticeFailure(result.turn, result.task));
    } catch (e) {
      if (currentConversation.current !== conversationId) return true;
      // Revert a failed optimistic paint; retain the idempotency key for safe retry.
      setMessages(current => current.filter(message => message.id !== requestId));
      setDraft(prompt);
      setError(e instanceof Error ? e.message : "提交失败，重试会复用相同的请求标识。");
      setBusy(false);
    } finally {
      posting.current = false;
      setProgress("");
      input.current?.focus();
    }
    return true;
  }

  async function loadOlder() {
    if (!conversationId || olderCursor == null || loadingOlder || !ready) return;
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
    ready, checked, conversationId, conversationTitle, artifacts,
    activeTurn, olderCursor, loadingOlder, loadOlder, chatScroll, skipScroll,
    openArtifact, send, refresh: async () => {
      if (!conversationId || !ready) return;
      applyDetail(await getConversationQuery(ownerId!, "detail:" + conversationId, 0,
        () => conversationApi.get(conversationId), { force: true }));
    },
  };
}
