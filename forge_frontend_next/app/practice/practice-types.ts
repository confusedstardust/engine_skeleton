import type { TimelineEvent } from "./creation-timeline";
import type { AgentChoiceQuestion } from "./agent-choice-protocol";
import type { TaskUsageReceipt } from "./task-usage";
import type { LearningPlan } from "./live-progress";
import type { GeneratedWork } from "./generated-work-card";
import type { RpgMessageMetadata } from "../../lib/conversation-api";

/** User-visible, server-owned message; only short-lived render state is in React. */
export type PracticeMessage = {
  id?: string;
  seq?: number;
  role: "user" | "assistant";
  content: string;
  choices?: AgentChoiceQuestion;
  billing?: TaskUsageReceipt;
  timeline?: TimelineEvent[];
  durationMs?: number;
  learningPlan?: LearningPlan;
  publicBrief?: string;
  work?: GeneratedWork;
  rpg?: RpgMessageMetadata;
  rpgEditJobId?: string;
};
