import { createApiClient } from "./api-client";

export type BoardQuestion = { id: string; kind?: "QUESTION" | "SUGGESTION"; question: string; answer: string | null; published?: boolean; author_name?: string; created_at: string };
export type BoardNotice = { id: string; title: string; content: string; published?: boolean; created_at: string };
export type BoardData = { announcements: BoardNotice[]; questions: BoardQuestion[]; has_more: boolean };

export const boardApi = createApiClient("/api/forge", {
  headers: { "X-Forge-Community-Action": "1", "X-Forge-Admin-Action": "1" },
  errorMessage: "暂时无法连接，请稍后重试",
});

