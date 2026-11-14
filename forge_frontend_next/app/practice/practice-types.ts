import type { SessionMessage } from "./practice-session";

// Session and live-render messages share a single contract.
export type PracticeMessage = SessionMessage;
export type ChatReply = { id: string; output: string; duration_ms?: number };
