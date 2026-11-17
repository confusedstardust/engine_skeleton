import { workApi, type SavedWork, type SavedWorkVersion } from "../../lib/work-api";
import type { WorkPreviewData } from "./work-inspector";

/** The canonical projection of a versioned, owner-checked work into a preview. */
export function savedWorkPreview(work: SavedWork, version: SavedWorkVersion, html: string): WorkPreviewData {
  return {
    artifactId: version.artifact_id, html, title: work.title,
    kind: work.kind, version: version.version_number,
    workId: work.id, savedArtifactId: version.artifact_id,
    currentVersionId: version.id, latestVersionId: work.current_version_id,
    versions: work.versions, isHistorical: version.id !== work.current_version_id,
    publicationStatus: work.publication_status, publicUrl: work.public_url,
    summary: work.summary, subject: work.subject, grade: work.grade, tags: work.tags,
    coverVariant: work.cover_variant,
  };
}

/** Both history navigation and deep links must use the same owner-scoped read. */
export async function loadSavedWork(workId: string, versionId?: string): Promise<WorkPreviewData> {
  const { work } = await workApi.get(workId);
  const targetId = versionId || work.current_version_id;
  const version = work.versions.find(item => item.id === targetId);
  if (!version) throw new Error("该作品版本已不存在");
  const blob = await workApi.html(work.id, version.id);
  return savedWorkPreview(work, version, await blob.text());
}

/** One save/attach implementation; publication can use a stricter lineage requirement. */
export async function persistArtifact(
  item: WorkPreviewData,
  options: { title?: string; summary?: string; strictParent?: boolean } = {},
): Promise<SavedWork | null> {
  if (item.workId && item.savedArtifactId === item.artifactId) return null;
  if (!item.workId) return (await workApi.save({
    artifact_id: item.artifactId,
    kind: item.kind, title: options.title ?? item.title,
    ...(options.summary !== undefined ? { summary: options.summary } : {}),
  })).work;

  const parentId = options.strictParent ? item.expectedParentArtifactId
    : item.expectedParentArtifactId || item.savedArtifactId;
  if (!parentId) throw new Error("旧版信息不完整，请重新打开作品后重试");
  return (await workApi.attachVersion(item.workId, item.artifactId, parentId)).work;
}
