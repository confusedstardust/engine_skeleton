import { forgeApi } from "./api-client";

export type SavedWorkVersion = {
  id: string;
  artifact_id: string;
  version_number: number;
  created_at: string;
};

export type SavedWork = {
  id: string;
  kind: "html" | "animation";
  title: string;
  summary: string;
  subject?: string | null;
  grade?: string | null;
  tags: string[];
  current_version_id: string;
  versions: SavedWorkVersion[];
  publication_status: "draft" | "publishing" | "published" | "failed" | "unpublished";
  created_at: string;
  updated_at: string;
};

const mutationHeaders = { "X-NarAgent-Action": "chat" };

export const workApi = {
  list: () => forgeApi<{ works: SavedWork[] }>("/works"),
  get: (id: string) => forgeApi<{ work: SavedWork }>(`/works/${id}`),
  save: (payload: { artifact_id: string; kind: "html" | "animation"; title: string; summary?: string }) =>
    forgeApi<{ work: SavedWork }>("/works", {
      method: "POST", headers: mutationHeaders, body: JSON.stringify(payload),
    }),
  attachVersion: (id: string, artifactId: string, parentArtifactId: string) =>
    forgeApi<{ work: SavedWork }>(`/works/${id}/versions`, {
      method: "POST", headers: mutationHeaders,
      body: JSON.stringify({ artifact_id: artifactId, expected_parent_artifact_id: parentArtifactId }),
    }),
  update: (id: string, fields: Partial<Pick<SavedWork, "title" | "summary" | "subject" | "grade" | "tags">>) =>
    forgeApi<{ work: SavedWork }>(`/works/${id}`, {
      method: "PATCH", headers: mutationHeaders, body: JSON.stringify(fields),
    }),
  html: (id: string, versionId: string) =>
    forgeApi.blob(`/works/${id}/assets/${versionId}/index.html`),
};
