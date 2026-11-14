import { forgeApi } from "./api-client";

export type ConversationSummary = {
  id: string;
  title: string;
  createdAt: string;
  activeAt: string;
};

export type ServerMessage = {
  id: string;
  seq: number;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
  metadata?: {
    timeline?: unknown[];
    publicBrief?: string;
    learningPlan?: unknown;
    elapsedMs?: number;
  } | null;
};

export type ConversationArtifact = {
  artifactId: string;
  conversationId: string;
  originMessageId?: string | null;
  workId: string | null;
  title: string;
  kind: "html" | "animation";
  createdAt: string;
  sources?: { conversationId: string; title: string }[];
};

export type ServerTurn = {
  id: string;
  conversationId: string;
  status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "UNKNOWN";
  mode: "chat" | "html" | "animation" | "edit";
  runId: string | null;
  errorCode: string | null;
  parentArtifactId: string | null;
  createdAt: string;
};

export type ConversationDetail = {
  conversation: ConversationSummary;
  messages: ServerMessage[];
  nextBefore: number | null;
  activeTurn: ServerTurn | null;
  artifacts: ConversationArtifact[];
};

export type SubmitResult = {
  conversationId: string;
  turn: ServerTurn;
  reused?: boolean;
  task?: Record<string, unknown>;
};

const mutationHeaders = { "X-NarAgent-Action": "chat" };
const base = "/nar-agent";

export const conversationApi = {
  status: () => forgeApi<{ enabled: boolean }>(base + "/conversations/status"),
  list: (cursor?: string) =>
    forgeApi<{ items: ConversationSummary[]; nextCursor: string | null }>(
      base + "/conversations?limit=30" + (cursor ? "&cursor=" + encodeURIComponent(cursor) : "")),
  get: (id: string) => forgeApi<ConversationDetail>(base + "/conversations/" + id),
  messages: (id: string, before: number) =>
    forgeApi<{ items: ServerMessage[]; nextBefore: number | null }>(
      base + "/conversations/" + id + "/messages?before=" + before + "&limit=30"),
  artifacts: (cursor?: string) =>
    forgeApi<{ items: ConversationArtifact[]; nextCursor: string | null }>(
      base + "/artifact-history?limit=30" + (cursor ? "&cursor=" + encodeURIComponent(cursor) : "")),
  create: (id: string, requestId: string, prompt: string,
           mode: "chat" | "html" | "animation" | "edit",
           parentArtifactId?: string) =>
    forgeApi<SubmitResult>(base + "/conversations", {
      method: "POST", headers: mutationHeaders,
      body: JSON.stringify({
        conversation_id: id, client_request_id: requestId, prompt, mode,
        ...(parentArtifactId ? { parent_artifact_id: parentArtifactId } : {}),
      }),
    }),
  turn: (id: string, requestId: string, prompt: string,
         mode: "chat" | "html" | "animation" | "edit",
         parentArtifactId?: string) =>
    forgeApi<SubmitResult>(base + "/conversations/" + id + "/turns", {
      method: "POST", headers: mutationHeaders,
      body: JSON.stringify({
        client_request_id: requestId, prompt, mode,
        ...(parentArtifactId ? { parent_artifact_id: parentArtifactId } : {}),
      }),
    }),
  turnStatus: (id: string, turnId: string) =>
    forgeApi<{ turn: ServerTurn; task?: Record<string, unknown> }>(
      base + "/conversations/" + id + "/turns/" + turnId),
  associateWork: (id: string, artifactId: string, workId: string) =>
    forgeApi<{ linked: boolean }>(base + "/conversations/" + id + "/artifacts", {
      method: "POST", headers: mutationHeaders,
      body: JSON.stringify({ artifact_id: artifactId, work_id: workId }),
    }),
};
