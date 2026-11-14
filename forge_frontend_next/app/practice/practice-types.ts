import type { TimelineEvent } from "./creation-timeline";
import type { LearningPlan } from "./live-progress";
import type { GeneratedWork } from "./generated-work-card";

export type PracticeMessage = {
  role: "user" | "assistant";
  content: string;
  timeline?: TimelineEvent[];
  durationMs?: number;
  learningPlan?: LearningPlan;
  publicBrief?: string;
  work?: GeneratedWork;
};

export type ChatReply = { id: string; output: string; duration_ms?: number };
