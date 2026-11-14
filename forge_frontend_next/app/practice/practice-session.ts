import type { TimelineEvent } from "./creation-timeline";
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

export function readPracticeSession(owner: string): PracticeSession | null {
  if (!owner || typeof sessionStorage === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(PREFIX + owner);
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

export function writePracticeSession(owner: string, data: PracticeSession) {
  if (!owner || typeof sessionStorage === "undefined") return;
  try {
    sessionStorage.setItem(PREFIX + owner, JSON.stringify({
      ...data, messages: data.messages.slice(-40), works: data.works.slice(-30),
    }));
  } catch { /* Browsers may disable session storage; generation still works. */ }
}

export function clearPracticeSession(owner: string) {
  if (!owner || typeof sessionStorage === "undefined") return;
  try { sessionStorage.removeItem(PREFIX + owner); }
  catch { /* No-op when private storage is disabled. */ }
}
