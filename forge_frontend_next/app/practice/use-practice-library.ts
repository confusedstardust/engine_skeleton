"use client";

import { useState, type Dispatch, type SetStateAction } from "react";
import { workApi, type PublicationForm, type SharedWork } from "../../lib/work-api";
import { loadSavedWork, persistArtifact } from "./practice-work-service";
import type { WorkPreviewData } from "./work-inspector";
import type { PracticeMessage } from "./practice-types";

type Args = {
  workPreviews: Record<string, WorkPreviewData>;
  setWorkPreviews: Dispatch<SetStateAction<Record<string, WorkPreviewData>>>;
  setMessages: Dispatch<SetStateAction<PracticeMessage[]>>;
  loggedIn: boolean;
  busy: boolean;
  setError: Dispatch<SetStateAction<string>>;
  setSelectedArtifactId: Dispatch<SetStateAction<string | null>>;
  setCurrentArtifactId: Dispatch<SetStateAction<string | null>>;
};

/** Save/version/publish/share controls. Conversation and generator state belong elsewhere. */
export function usePracticeLibrary({
  workPreviews, setWorkPreviews, setMessages, loggedIn, busy, setError,
  setSelectedArtifactId, setCurrentArtifactId,
}: Args) {
  const [savingArtifactId, setSavingArtifactId] = useState<string | null>(null);
  const [publishArtifactId, setPublishArtifactId] = useState<string | null>(null);
  const [metadataArtifactId, setMetadataArtifactId] = useState<string | null>(null);
  const [metadataBusy, setMetadataBusy] = useState(false);
  const [metadataError, setMetadataError] = useState("");
  const [revokeArtifactId, setRevokeArtifactId] = useState<string | null>(null);
  const [publicationBusy, setPublicationBusy] = useState(false);
  const [publicationError, setPublicationError] = useState("");
  const [revokeError, setRevokeError] = useState("");
  const [shareData, setShareData] = useState<SharedWork | null>(null);
  async function saveWork(artifactId: string) {
    const work = workPreviews[artifactId];
    if (!loggedIn || !work || savingArtifactId || (work.workId && work.savedArtifactId === artifactId)) return;
    setSavingArtifactId(artifactId);
    setError("");
    try {
      const saved = await persistArtifact(work);
      if (!saved) return;
      const version = saved.versions.find(item => item.id === saved.current_version_id);
      if (!version) throw new Error("作品版本保存失败");
      setWorkPreviews(previous => ({
        ...previous,
        [artifactId]: {
          ...previous[artifactId], workId: saved.id, title: saved.title,
          savedArtifactId: artifactId, currentVersionId: version.id,
          version: version.version_number,
          publicationStatus: saved.publication_status, publicUrl: saved.public_url,
          summary: saved.summary, subject: saved.subject, grade: saved.grade, tags: saved.tags,
          coverVariant: saved.cover_variant,
          versions: saved.versions, latestVersionId: saved.current_version_id, isHistorical: false,
        },
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存作品失败，请重试");
    } finally { setSavingArtifactId(null); }
  }


  async function viewSavedVersion(workId: string, versionId: string) {
    if (busy) return;
    setError("");
    try {
      const entry = await loadSavedWork(workId, versionId);
      setWorkPreviews(previous => ({ ...previous, [entry.artifactId]: entry }));
      setSelectedArtifactId(entry.artifactId);
      if (!entry.isHistorical) setCurrentArtifactId(entry.artifactId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "读取历史版本失败");
    }
  }

  async function saveMetadata(payload: PublicationForm) {
    const item = metadataArtifactId ? workPreviews[metadataArtifactId] : undefined;
    if (!item?.workId || metadataBusy) return;
    setMetadataBusy(true); setMetadataError("");
    try {
      const result = await workApi.update(item.workId, payload);
      setWorkPreviews(previous => ({
        ...previous,
        [item.artifactId]: {
          ...previous[item.artifactId], title: result.work.title, summary: result.work.summary,
          subject: result.work.subject, grade: result.work.grade, tags: result.work.tags,
          coverVariant: result.work.cover_variant,
        },
      }));
      setMessages(previous => previous.map(message => message.work?.artifactId === item.artifactId
        ? { ...message, work: { ...message.work, title: result.work.title } } : message));
      setMetadataArtifactId(null);
    } catch (err) {
      setMetadataError(err instanceof Error ? err.message : "作品资料保存失败");
    } finally { setMetadataBusy(false); }
  }

  async function submitPublication(payload: PublicationForm) {
    const item = publishArtifactId ? workPreviews[publishArtifactId] : undefined;
    if (!item || item.kind !== "html" || publicationBusy) return;
    setPublicationBusy(true); setPublicationError(""); setError("");
    try {
      // One publish action handles the underlying save/version step automatically.
      // Never expose an unpublished artifact URL or bypass the explicit publish modal.
      const saved = await persistArtifact(item, {
        title: payload.title, summary: payload.summary, strictParent: true,
      });
      const workId = saved?.id || item.workId;
      if (!workId) throw new Error("作品尚未保存，请重试");
      if (saved) {
        const latest = saved.versions.find(version => version.id === saved.current_version_id);
        setWorkPreviews(previous => ({
          ...previous,
          [item.artifactId]: {
            ...previous[item.artifactId], workId,
            savedArtifactId: item.artifactId,
            currentVersionId: latest?.id, version: latest?.version_number || item.version,
            versions: saved.versions, latestVersionId: saved.current_version_id, isHistorical: false,
          },
        }));
      }
      const result = await workApi.publish(workId, payload);
      if (!result.published) throw new Error("教师资源广场尚未确认发布");
      setWorkPreviews(previous => ({
        ...previous,
        [item.artifactId]: {
          ...previous[item.artifactId], workId, title: payload.title,
          publicationStatus: "published", publicUrl: result.public_url,
          summary: payload.summary, subject: payload.subject, grade: payload.grade, tags: payload.tags,
        },
      }));
      setPublishArtifactId(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "发布失败，请重试";
      setError(message);
      setPublicationError(message);
    } finally { setPublicationBusy(false); }
  }

  async function revokePublication() {
    const item = revokeArtifactId ? workPreviews[revokeArtifactId] : undefined;
    if (!item?.workId || publicationBusy) return;
    setPublicationBusy(true); setError("");
    try {
      await workApi.unpublish(item.workId);
      setWorkPreviews(previous => ({
        ...previous,
        [item.artifactId]: { ...previous[item.artifactId], publicationStatus: "unpublished", publicUrl: null },
      }));
      setRevokeArtifactId(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "撤回未完成，请重试";
      setError(message);
      setRevokeError(message);
      // Remote de-indexing can fail after the server has revoked all public reads.
      // Always refresh authoritative publication status to disable stale Share buttons.
      if (item.workId) {
        try {
          const status = await workApi.publication(item.workId);
          setWorkPreviews(previous => ({
            ...previous,
            [item.artifactId]: {
              ...previous[item.artifactId], publicationStatus: status.status,
              publicUrl: status.public_url,
            },
          }));
        } catch { /* Keep the error; the server remains authoritative. */ }
      }
    } finally { setPublicationBusy(false); }
  }

  async function openShare(artifactId: string) {
    const item = workPreviews[artifactId];
    if (!item?.workId || item.publicationStatus !== "published") return;
    setError("");
    try {
      // The server rejects private/unpublished/revoked works, regardless of UI state.
      const result = await workApi.share(item.workId);
      setShareData(result);
    } catch (error) {
      setError(error instanceof Error ? error.message : "当前作品无法分享");
    }
  }


  return {
    savingArtifactId, publishArtifactId, setPublishArtifactId,
    metadataArtifactId, setMetadataArtifactId, metadataBusy, metadataError, setMetadataError,
    revokeArtifactId, setRevokeArtifactId, publicationBusy, publicationError, setPublicationError,
    revokeError, setRevokeError, shareData, setShareData,
    saveWork, viewSavedVersion, saveMetadata, submitPublication, revokePublication, openShare,
  };
}
