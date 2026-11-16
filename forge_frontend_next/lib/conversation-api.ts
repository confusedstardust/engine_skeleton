import { forgeApi } from "./api-client";
import type { ClarificationAnswerV2 } from "../app/practice/agent-choice-protocol";

export type ConversationSummary = {
  id: string;
  title: string;
  pinned?: boolean;
  createdAt: string;
  activeAt: string;
};

export type RpgMessageMetadata = {
  schema_version: number;
  state: "PREPARED" | "CANCELLED" | "CLAIMED" | "JOB_CREATED" | "STARTING" | "STARTED" | "START_REJECTED" | "NEEDS_REVIEW";
  spec_version: number;
  spec: {
    topic: string;
    source_ref: { type: string };
    duration_minutes: number;
    generate_images: boolean;
    enable_voice: boolean;
  };
  job_id: string | null;
  confirmed_options?: { durationMinutes: number; generateImages: boolean; enableVoice: boolean } | null;
  last_error_code?: string | null;
};

export type RpgCardStatus = {
  messageId: string;
  state: RpgMessageMetadata["state"];
  specVersion: number;
  spec: {
    topic: string;
    sourceSummary: string;
    durationMinutes: number;
    generateImages: boolean;
    enableVoice: boolean;
  };
  jobId: string | null;
  canConfirm: boolean;
  confirmedOptions: { durationMinutes: number; generateImages: boolean; enableVoice: boolean } | null;
  lastErrorCode: string | null;
};

export type RpgSelections = {
  specVersion: number;
  durationMinutes: number;
  generateImages: boolean;
  enableVoice: boolean;
};

export type RpgQuote = {
  holdCredits: number;
  optionsValid: boolean;
  sufficientBalance: boolean;
  description: string;
};

export type RpgJobStatus = {
  id: string;
  status: string;
  phase: string | null;
  build_state?: string;
  has_published_build?: boolean;
  error?: string | null;
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
    choices?: import("../app/practice/agent-choice-protocol").AgentChoiceQuestion;
    billing?: import("../app/practice/task-usage").TaskUsageReceipt;
    card_type?: "rpg";
    rpg?: RpgMessageMetadata;
    rpg_edit_link?: { job_id: string };
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
  status: () => forgeApi<{ ready: boolean }>(base + "/conversations/status"),
  list: (cursor?: string) =>
    forgeApi<{ items: ConversationSummary[]; nextCursor: string | null }>(
      base + "/conversations?limit=30" + (cursor ? "&cursor=" + encodeURIComponent(cursor) : "")),
  get: (id: string) => forgeApi<ConversationDetail>(base + "/conversations/" + id),
  update: (id: string, values: { title?: string; pinned?: boolean }) =>
    forgeApi<ConversationSummary>(base + "/conversations/" + id, {
      method: "PATCH", headers: mutationHeaders, body: JSON.stringify(values),
    }),
  remove: (id: string) => forgeApi<{ deleted: boolean }>(base + "/conversations/" + id, {
    method: "DELETE", headers: mutationHeaders,
  }),
  messages: (id: string, before: number) =>
    forgeApi<{ items: ServerMessage[]; nextBefore: number | null }>(
      base + "/conversations/" + id + "/messages?before=" + before + "&limit=30"),
  artifacts: (cursor?: string) =>
    forgeApi<{ items: ConversationArtifact[]; nextCursor: string | null }>(
      base + "/artifact-history?limit=30" + (cursor ? "&cursor=" + encodeURIComponent(cursor) : "")),
  create: (id: string, requestId: string, prompt: string,
           mode: "auto" | "chat" | "html" | "animation" | "edit",
           parentArtifactId?: string, selectedArtifactId?: string) =>
    forgeApi<SubmitResult>(base + "/conversations", {
      method: "POST", headers: mutationHeaders,
      body: JSON.stringify({
        conversation_id: id, client_request_id: requestId, prompt, mode,
        ...(parentArtifactId ? { parent_artifact_id: parentArtifactId } : {}),
        ...(selectedArtifactId ? { selected_artifact_id: selectedArtifactId } : {}),
      }),
    }),
  turn: (id: string, requestId: string, prompt: string,
         mode: "auto" | "chat" | "html" | "animation" | "edit",
         parentArtifactId?: string, selectedArtifactId?: string) =>
    forgeApi<SubmitResult>(base + "/conversations/" + id + "/turns", {
      method: "POST", headers: mutationHeaders,
      body: JSON.stringify({
        client_request_id: requestId, prompt, mode,
        ...(parentArtifactId ? { parent_artifact_id: parentArtifactId } : {}),
        ...(selectedArtifactId ? { selected_artifact_id: selectedArtifactId } : {}),
      }),
    }),
  /** Optional real SSE for chat. HTML/animation retain the existing JSON job contract. */
  stream: async (
    id: string, requestId: string, prompt: string,
    mode: "auto" | "chat" | "html" | "animation" | "edit",
    parentArtifactId: string | undefined, isNew: boolean,
    handlers: {
      onAccepted?: (result: SubmitResult) => void;
      onText?: (text: string) => void;
    } = {},
    clarificationAnswer?: ClarificationAnswerV2,
    selectedArtifactId?: string,
  ): Promise<SubmitResult> => {
    const path = base + "/conversations/" +
      (isNew ? "stream" : id + "/turns/stream");
    const response = await forgeApi.response(path, {
      method: "POST",
      headers: { ...mutationHeaders, Accept: "text/event-stream" },
      body: JSON.stringify({
        ...(isNew ? { conversation_id: id } : {}),
        client_request_id: requestId, prompt, mode,
        ...(parentArtifactId ? { parent_artifact_id: parentArtifactId } : {}),
        ...(selectedArtifactId ? { selected_artifact_id: selectedArtifactId } : {}),
        ...(clarificationAnswer ? { clarification_answer: clarificationAnswer } : {}),
      }),
    });
    if (!(response.headers.get("content-type") ?? "").includes("text/event-stream")) {
      return await response.json() as SubmitResult;
    }
    if (!response.body) throw new Error("服务器未返回流式响应内容");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let result: SubmitResult | undefined;
    let streamedText = "";
    const consume = (frame: string) => {
      let event = "";
      const data: string[] = [];
      for (const line of frame.split(/\r?\n/)) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
      }
      if (!event || !data.length) return;
      const value = JSON.parse(data.join("\n")) as Record<string, unknown>;
      if (event === "accepted") {
        handlers.onAccepted?.(value as SubmitResult);
      } else if (event === "delta" && typeof value.text === "string") {
        streamedText += value.text;
        handlers.onText?.(streamedText);
      } else if (event === "replace" && typeof value.text === "string") {
        streamedText = value.text;
        handlers.onText?.(streamedText);
      } else if (event === "result") {
        result = value as SubmitResult;
      }
    };
    try {
      while (true) {
        const { done, value } = await reader.read();
        buffer += decoder.decode(value, { stream: !done });
        const normalized = buffer.replace(/\r\n/g, "\n");
        buffer = normalized;
        let cut: number;
        while ((cut = buffer.indexOf("\n\n")) >= 0) {
          consume(buffer.slice(0, cut));
          buffer = buffer.slice(cut + 2);
        }
        if (done) break;
      }
    } finally { reader.releaseLock(); }
    if (!result) throw new Error("流式连接中断，请刷新会话确认执行结果，勿重复提交");
    return result;
  },
  turnStatus: (id: string, turnId: string) =>
    forgeApi<{ turn: ServerTurn; task?: Record<string, unknown> }>(
      base + "/conversations/" + id + "/turns/" + turnId),
  rpgStatus: (id: string, messageId: string) =>
    forgeApi<RpgCardStatus>(base + "/conversations/" + id + "/messages/" + messageId + "/rpg"),
  rpgQuote: (id: string, messageId: string, selections: RpgSelections) =>
    forgeApi<RpgQuote>(base + "/conversations/" + id + "/messages/" + messageId + "/rpg/quote", {
      method: "POST", headers: mutationHeaders, body: JSON.stringify(selections),
    }),
  rpgConfirm: (id: string, messageId: string, selections: RpgSelections, acceptedHoldCredits: number) =>
    forgeApi<RpgCardStatus>(base + "/conversations/" + id + "/messages/" + messageId + "/rpg/confirm", {
      method: "POST", headers: mutationHeaders,
      body: JSON.stringify({ ...selections, acceptedHoldCredits }),
    }),
  rpgCancel: (id: string, messageId: string) =>
    forgeApi<RpgCardStatus>(base + "/conversations/" + id + "/messages/" + messageId + "/rpg/cancel", {
      method: "POST", headers: mutationHeaders,
    }),
  rpgJob: (jobId: string) => forgeApi<RpgJobStatus>("/jobs/" + jobId),
  associateWork: (id: string, artifactId: string, workId: string) =>
    forgeApi<{ linked: boolean }>(base + "/conversations/" + id + "/artifacts", {
      method: "POST", headers: mutationHeaders,
      body: JSON.stringify({ artifact_id: artifactId, work_id: workId }),
    }),
};
