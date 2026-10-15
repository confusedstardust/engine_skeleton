import { withBasePath } from "../app/base-path";
import { jsonAuthHeaders } from "../app/invite-identity";

export type BoardQuestion = { id: string; kind?: "QUESTION" | "SUGGESTION"; question: string; answer: string | null; published?: boolean; author_name?: string; created_at: string };
export type BoardNotice = { id: string; title: string; content: string; published?: boolean; created_at: string };
export type BoardData = { announcements: BoardNotice[]; questions: BoardQuestion[]; has_more: boolean };

export async function boardApi<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = jsonAuthHeaders();
  headers.set("X-Forge-Community-Action", "1");
  headers.set("X-Forge-Admin-Action", "1");
  const response = await fetch(withBasePath(`/api/forge${path}`), { ...init, credentials: "include", cache: "no-store", headers });
  if (!response.ok) {
    let detail = "暂时无法连接，请稍后重试";
    try { const body = await response.json(); if (typeof body.detail === "string") detail = body.detail; } catch { /* Non-JSON service error. */ }
    throw Object.assign(new Error(detail), { status: response.status });
  }
  return response.json() as Promise<T>;
}

