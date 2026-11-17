"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { BookOpenCheck, FolderOpen, PencilLine, Send, Share2, Undo2 } from "lucide-react";
import { Button } from "../../components/ui/button";
import { CloseButton } from "../../components/ui/close-button";
import AnimationPreview from "./animation-preview";
import type { GeneratedWork } from "./generated-work-card";
import type { SavedWorkVersion } from "../../lib/work-api";
import styles from "./practice.module.css";

export type WorkPreviewData = GeneratedWork & {
  html: string;
  workId?: string;
  savedArtifactId?: string;
  currentVersionId?: string;
  expectedParentArtifactId?: string;
  publicationStatus?: string;
  publicUrl?: string | null;
  summary?: string;
  subject?: string | null;
  grade?: string | null;
  tags?: string[];
  coverVariant?: "preview" | "mobile";
  versions?: SavedWorkVersion[];
  latestVersionId?: string;
  isHistorical?: boolean;
};

export default function WorkInspector({
  work, onClose, onSave, onEditMetadata, onViewVersion, onPublish, onUnpublish, onShare,
  saving = false, publishing = false,
}: {
  work: WorkPreviewData;
  onClose: () => void;
  onSave: (id: string) => void;
  onEditMetadata: (id: string) => void;
  onViewVersion: (workId: string, versionId: string) => void;
  onPublish: (id: string) => void;
  onUnpublish: (id: string) => void;
  onShare: (id: string) => void;
  saving?: boolean;
  publishing?: boolean;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const closeHandler = useRef(onClose);
  useEffect(() => { closeHandler.current = onClose; }, [onClose]);
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeHandler.current();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [work.artifactId]);

  const saved = Boolean(work.workId && work.savedArtifactId === work.artifactId);
  const published = work.publicationStatus === "published";
  const historical = Boolean(work.isHistorical);

  return <aside className={styles.inspector} aria-label={`作品预览：${work.title}`}>
    <header className={styles.inspectorHeader}>
      <div><strong>{work.title}</strong><span>互动作品 · V{work.version} · {saved ? "已保存" : "尚未保存"}</span></div>
      <CloseButton ref={closeRef} size="sm" aria-label="关闭作品预览" onClick={onClose} />
    </header>
    <div className={styles.inspectorScroll}>
      {saved && work.versions && work.versions.length > 1 &&
        <div className={styles.versionPicker}>
          <label htmlFor="work-version-select">作品版本</label>
          <select id="work-version-select" value={work.currentVersionId || ""}
            onChange={event => onViewVersion(work.workId!, event.target.value)}>
            {work.versions.map(version => <option key={version.id} value={version.id}>
              V{version.version_number} · {new Date(version.created_at).toLocaleDateString("zh-CN")}
            </option>)}
          </select>
          {historical && <p>正在查看历史版本。请切回最新版本再继续编辑、保存或发布。</p>}
        </div>}
      <AnimationPreview html={work.html} label="互动作品预览" compact />
      <div className={styles.inspectorActions}>
        {saved && work.workId ? (
          <Link href="/history" className={`${styles.inspectorAction} ${styles.inspectorActionPrimary}`}>
            <FolderOpen size={17} aria-hidden="true" strokeWidth={1.8} />
            <span>在我的作品中查看</span>
          </Link>
        ) : (
          <Button variant="unstyled" className={`${styles.inspectorAction} ${styles.inspectorActionPrimary}`}
            disabled={historical || saving} busy={saving} onClick={() => onSave(work.artifactId)}>
            <BookOpenCheck size={17} aria-hidden="true" strokeWidth={1.8} />
            <span>{work.workId ? "保存新版本" : "保存到我的作品"}</span>
          </Button>
        )}
        {saved && !historical && <Button variant="unstyled" className={styles.inspectorAction}
          onClick={() => onEditMetadata(work.artifactId)}>
          <PencilLine size={17} aria-hidden="true" strokeWidth={1.8} /><span>编辑作品信息</span>
        </Button>}
        {!historical && (published
          ? <Button variant="unstyled" className={styles.inspectorAction} disabled={publishing}
              busy={publishing} onClick={() => onUnpublish(work.artifactId)}>
              <Undo2 size={17} aria-hidden="true" strokeWidth={1.8} /><span>撤回发布</span>
            </Button>
          : <Button variant="unstyled" className={styles.inspectorAction}
              disabled={publishing || saving} busy={publishing} onClick={() => onPublish(work.artifactId)}>
              <Send size={17} aria-hidden="true" strokeWidth={1.8} />
              <span>{saved ? "发布到教师资源广场" : "保存并发布到广场"}</span>
            </Button>)}
        <Button variant="unstyled" className={styles.inspectorAction} onClick={() => onShare(work.artifactId)}>
          <Share2 size={17} aria-hidden="true" strokeWidth={1.8} /><span>分享作品</span>
        </Button>
      </div>
    </div>
  </aside>;
}
