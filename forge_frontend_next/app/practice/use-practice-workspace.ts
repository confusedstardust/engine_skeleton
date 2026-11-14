"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { forgeApi } from "../../lib/api-client";
import { conversationApi } from "../../lib/conversation-api";
import { loadSavedWork } from "./practice-work-service";
import { usePracticeLibrary } from "./use-practice-library";
import { useNarConversation } from "./use-nar-conversation";
import type { WorkPreviewData } from "./work-inspector";
import type { GeneratedWork } from "./generated-work-card";
import type { BuildTask } from "./live-progress";
import type { PracticeMessage } from "./practice-types";

/**
 * One authenticated conversation source of truth: Forge /nar-agent/conversations.
 * Browser state is ephemeral rendering only; no chat history is persisted to
 * browser storage or reconstructed from unrelated saved works.
 *
 * Legacy /practice/?work=<id> remains a saved-work preview deep link. It never
 * implies that a historical conversation can be inferred from a work's HTML.
 */
export function usePracticeWorkspace(workspaceScope = "general", conversationId?: string) {
  const router = useRouter();
  const [messages, setMessages] = useState<PracticeMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loginRequired, setLoginRequired] = useState(false);
  const [loggedIn, setLoggedIn] = useState(false);
  const [sessionUserId, setSessionUserId] = useState<string | null>(null);
  const [userAvatarUrl, setUserAvatarUrl] = useState<string | null>(null);
  const [userInitial, setUserInitial] = useState("");
  const [sessionReady, setSessionReady] = useState(false);
  const [authReady, setAuthReady] = useState(false);
  const [progress, setProgress] = useState("");
  const [activeTask, setActiveTask] = useState<BuildTask | null>(null);
  const [workPreviews, setWorkPreviews] = useState<Record<string, WorkPreviewData>>({});
  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(null);
  const [currentArtifactId, setCurrentArtifactId] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const previousScope = useRef(workspaceScope);

  const server = useNarConversation({
    conversationId, authReady, loggedIn, ownerId: sessionUserId,
    setSessionReady, setMessages, setWorkPreviews,
    setSelectedArtifactId, setCurrentArtifactId, setBusy, setActiveTask,
    setError, setDraft, setProgress, input,
  });
  const library = usePracticeLibrary({
    workPreviews, setWorkPreviews, setMessages, loggedIn, busy, setError,
    setSelectedArtifactId, setCurrentArtifactId,
    onSaved: conversationId ? async (artifactId, workId) => {
      await conversationApi.associateWork(conversationId, artifactId, workId);
    } : undefined,
  });
  const {
    publishArtifactId, metadataArtifactId, setPublishArtifactId,
    setMetadataArtifactId, setRevokeArtifactId, setShareData,
  } = library;
  const selectedWork = selectedArtifactId ? workPreviews[selectedArtifactId] : undefined;
  const publishWork = publishArtifactId ? workPreviews[publishArtifactId] : undefined;
  const metadataWork = metadataArtifactId ? workPreviews[metadataArtifactId] : undefined;

  useEffect(() => {
    let active = true;
    forgeApi<{ auth_type?: string; id?: string; avatar_url?: string | null; nickname?: string | null }>("/auth/me").then(user => {
      if (!active) return;
      const isSso = user.auth_type === "sso" && Boolean(user.id);
      setLoggedIn(isSso);
      setLoginRequired(!isSso);
      setSessionUserId(isSso ? String(user.id) : null);
      const avatar = user.avatar_url?.trim();
      setUserAvatarUrl(isSso && avatar && /^(https?:\/\/|\/)/i.test(avatar) ? avatar : null);
      setUserInitial(isSso && user.nickname ? Array.from(user.nickname.trim())[0] || "" : "");
    }).catch(() => {
      if (active) { setLoggedIn(false); setLoginRequired(true); setSessionUserId(null); setUserAvatarUrl(null); setUserInitial(""); }
    }).finally(() => { if (active) setAuthReady(true); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!server.skipScroll.current && (messages.length || busy)) {
      end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [messages, busy, server.skipScroll]);

  useEffect(() => {
    if (previousScope.current === workspaceScope) return;
    previousScope.current = workspaceScope;
    setPublishArtifactId(null);
    setMetadataArtifactId(null);
    setRevokeArtifactId(null);
    setShareData(null);
    if (conversationId) return;
    setMessages([]); setWorkPreviews({});
    setSelectedArtifactId(null); setCurrentArtifactId(null);
    setError(""); setDraft(""); setSessionReady(false);
  }, [workspaceScope, conversationId, setPublishArtifactId, setMetadataArtifactId, setRevokeArtifactId, setShareData]);

  useEffect(() => {
    // /practice/chat/:id is restored by the server hook.
    if (!authReady || !server.checked || conversationId) return;
    if (!loggedIn) { setSessionReady(true); return; }

    if (!/^[a-f0-9]{32}$/.test(workspaceScope)) {
      setSessionReady(true);
      return;
    }
    // This is an existing saved work, not a serialized conversation.
    let active = true;
    setSessionReady(false);
    void loadSavedWork(workspaceScope).then(work => {
      if (!active) return;
      setWorkPreviews({ [work.artifactId]: work });
      setCurrentArtifactId(work.artifactId);
      setSelectedArtifactId(work.artifactId);
    }).catch(e => {
      if (active) setError(e instanceof Error ? e.message : "作品读取失败");
    }).finally(() => { if (active) setSessionReady(true); });
    return () => { active = false; };
  }, [authReady, server.checked, loggedIn, workspaceScope, conversationId]);

  async function send(mode: "chat" | "animation" | "html" | "edit" = "chat") {
    const prompt = draft.trim();
    if (!prompt || busy || !authReady || !loggedIn || !sessionReady || !server.checked) return;
    if (!server.ready) {
      setError("会话数据库尚未准备好，请先执行 002_nar_conversation_history.sql 迁移；消息不会保存在浏览器。");
      return;
    }
    const selected = currentArtifactId ? workPreviews[currentArtifactId] : undefined;
    const parent = mode === "edit" && selected?.kind === "html" ? selected.artifactId : undefined;
    await server.send(prompt, mode, parent);
  }

  function savedCardWorkId(work: GeneratedWork): string | undefined {
    const preview = workPreviews[work.artifactId];
    return preview?.savedArtifactId === work.artifactId ? preview.workId :
      server.artifacts.find(artifact => artifact.artifactId === work.artifactId)?.workId ?? undefined;
  }

  function beginNewConversation() {
    if (busy) return;
    if (conversationId || workspaceScope !== "general") {
      router.push("/practice/");
      return;
    }
    // A session is created by its first valid user input, not by a sidebar click.
    setDraft("");
    setError("");
    setMessages([]);
    setWorkPreviews({});
    setSelectedArtifactId(null);
    setCurrentArtifactId(null);
    input.current?.focus();
  }

  const savedWorkCount = Object.values(workPreviews).filter(work => Boolean(work.workId)).length;
  return {
    workspaceScope, messages, draft, setDraft, busy, error, loginRequired, loggedIn,
    sessionUserId, userAvatarUrl, userInitial, sessionReady, authReady, progress, activeTask, workPreviews,
    selectedWork, publishWork, metadataWork, selectedArtifactId, setSelectedArtifactId,
    currentArtifactId, setCurrentArtifactId, end, input, savedWorkCount, send,
    beginNewConversation, savedCardWorkId,
    serverReady: server.ready, serverChecked: server.checked, conversationId,
    conversationTitle: server.conversationTitle,
    conversationArtifacts: server.artifacts, olderCursor: server.olderCursor,
    loadOlder: server.loadOlder, loadingOlder: server.loadingOlder,
    chatScroll: server.chatScroll, openArtifact: server.openArtifact,
    ...library,
  };
}
