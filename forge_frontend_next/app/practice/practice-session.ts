import type { TimelineEvent } from "./creation-timeline";
import type { LearningPlan } from "./live-progress";
import type { GeneratedWork } from "./generated-work-card";
import type { WorkPreviewData } from "./work-inspector";

/**
 * This tab-scoped, user-scoped record contains no HTML source or credentials.
 * The real work HTML is always fetched again through owner-checked Forge APIs.
 */
export type SessionMessage = {
  role: "user" | "assistant";
  content: string;
  timeline?: TimelineEvent[];
  durationMs?: number;
  learningPlan?: LearningPlan;
  publicBrief?: string;
  work?: GeneratedWork;
};
export type PendingCreation = {
  id: string;
  endpoint: "html" | "animations";
  mode: "html" | "edit" | "animation";
  prompt: string;
  parentArtifactId?: string | null;
  originalMessages: SessionMessage[];
  startedAt: number;
};
type CachedWork = Omit<WorkPreviewData, "html">;
export type PracticeSession = {
  messages: SessionMessage[];
  works: CachedWork[];
  currentArtifactId: string | null;
  selectedArtifactId: string | null;
  pending: PendingCreation | null;
};

const PREFIX = "narrativeos:practice:session:v1:";
const ID = /^[0-9a-f]{32}$/;

export function readPracticeSession(owner: string, workspace = "general"): PracticeSession | null {
  if (!owner || typeof sessionStorage === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(PREFIX + owner + ":" + workspace);
    if (!raw || raw.length > 250000) return null;
    const stored: unknown = JSON.parse(raw);
    if (!stored || typeof stored !== "object") return null;
    const value = stored as Partial<PracticeSession>;
    const messages = Array.isArray(value.messages) ? value.messages.filter(
      m => m && (m.role === "user" || m.role === "assistant") && typeof m.content === "string"
        && m.content.length <= 12000,
    ).slice(-40) : [];
    const works = Array.isArray(value.works) ? value.works.filter(
      w => w && typeof w.title === "string" && ID.test(w.artifactId) &&
        (w.kind === "html" || w.kind === "animation"),
    ).slice(-30) : [];
    const pending = value.pending && ID.test(value.pending.id) &&
      (value.pending.endpoint === "html" || value.pending.endpoint === "animations") &&
      (value.pending.mode === "html" || value.pending.mode === "animation" || value.pending.mode === "edit") &&
      typeof value.pending.prompt === "string" && value.pending.prompt.length <= 12000 &&
      Array.isArray(value.pending.originalMessages) && Number.isFinite(value.pending.startedAt)
      ? value.pending : null;
    return {
      messages,
      works,
      currentArtifactId: value.currentArtifactId && ID.test(value.currentArtifactId) ? value.currentArtifactId : null,
      selectedArtifactId: value.selectedArtifactId && ID.test(value.selectedArtifactId) ? value.selectedArtifactId : null,
      pending,
    };
  } catch { return null; }
}

export function writePracticeSession(owner: string, data: PracticeSession, workspace = "general") {
  if (!owner || typeof sessionStorage === "undefined") return;
  try {
    sessionStorage.setItem(PREFIX + owner + ":" + workspace, JSON.stringify({
      ...data, messages: data.messages.slice(-40), works: data.works.slice(-30),
    }));
  } catch { /* Browsers may disable session storage; generation still works. */ }
}

export function clearPracticeSession(owner: string, workspace = "general") {
  if (!owner || typeof sessionStorage === "undefined") return;
  try { sessionStorage.removeItem(PREFIX + owner + ":" + workspace); }
  catch { /* No-op when private storage is disabled. */ }
}

/** Recover only the unambiguous user prompt + generated reply for this saved work.
 * Do not assign unrelated general-chat turns to an arbitrary artifact. */
export function extractWorkConversation(
  messages: SessionMessage[],
  works: Array<Pick<WorkPreviewData, "artifactId" | "workId">>,
  workId: string,
): SessionMessage[] {
  const artifactIds = new Set(works.filter(w => w.workId === workId).map(w => w.artifactId));
  const selected = new Set<number>();
  messages.forEach((message, index) => {
    if (!message.work || !artifactIds.has(message.work.artifactId)) return;
    selected.add(index);
    if (index > 0 && messages[index - 1].role === "user") selected.add(index - 1);
  });
  return [...selected].sort((a, b) => a - b).map(index => messages[index]);
}

/** Existing per-work snapshots always win. Legacy general state is read-only source. */
export function recoverPracticeSession(owner: string, workspace: string): PracticeSession | null {
  const saved = readPracticeSession(owner, workspace);
  if (workspace === "general") return saved;
  if (saved) {
    const matching = saved.works.filter(work => work.workId === workspace);
    const containsForeignWork = saved.works.some(work => work.workId !== workspace);
    const matchingArtifacts = new Set(matching.map(work => work.artifactId));
    const containsForeignResult = saved.messages.some(message =>
      message.work && !matchingArtifacts.has(message.work.artifactId));
    if (matching.length && !containsForeignWork && !containsForeignResult) return saved;
    if (matching.length) {
      // Older SPA navigation could persist work A in B's session bucket.
      // Keep only generated turns that can be attributed to B.
      const messages = extractWorkConversation(saved.messages, saved.works, workspace);
      return {
        messages, works: matching,
        currentArtifactId: matching.some(w => w.artifactId === saved.currentArtifactId)
          ? saved.currentArtifactId : matching[matching.length - 1]?.artifactId ?? null,
        selectedArtifactId: matching.some(w => w.artifactId === saved.selectedArtifactId)
          ? saved.selectedArtifactId : matching[matching.length - 1]?.artifactId ?? null,
        pending: null,
      };
    }
    if (!saved.works.length && saved.messages.every(m => !m.work)) return saved;
    // Every referenced work belongs to another ID: don't show it as this work.
  }
  const general = readPracticeSession(owner, "general");
  if (!general) return null;
  const messages = extractWorkConversation(general.messages, general.works, workspace);
  if (!messages.length) return null;
  const works = general.works.filter(work => work.workId === workspace);
  return {
    messages,
    works,
    currentArtifactId: works.some(w => w.artifactId === general.currentArtifactId)
      ? general.currentArtifactId : works[works.length - 1]?.artifactId ?? null,
    selectedArtifactId: works.some(w => w.artifactId === general.selectedArtifactId)
      ? general.selectedArtifactId : works[works.length - 1]?.artifactId ?? null,
    pending: null,
  };
}
