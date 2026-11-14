"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { Button } from "../../components/ui/button";
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
  work, onClose, onEdit, onSave, onEditMetadata, onViewVersion, onPublish, onUnpublish, onShare, saving = false, publishing = false,
}: {
  work: WorkPreviewData;
  onClose: () => void;
  onEdit: (id: string) => void;
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
      <div><strong>{work.title}</strong><span>{work.kind === "html" ? "互动网页" : "教学动画"} · V{work.version} · {saved ? "已保存" : "尚未保存"}</span></div>
      <button ref={closeRef} type="button" aria-label="关闭作品预览" className={styles.inspectorClose} onClick={onClose}>×</button>
    </header>
    <div className={styles.inspectorScroll}>
      {work.workId && work.versions && work.versions.length > 1 &&
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
      <AnimationPreview html={work.html} artifactId={work.artifactId} label="互动作品预览" compact storedAssetsBase={work.workId && work.currentVersionId && work.savedArtifactId === work.artifactId ? `/api/forge/works/${work.workId}/assets/${work.currentVersionId}` : undefined} />
      <p className={styles.inspectorTip}>可直接操作预览中的控件。正式教学使用前，请核对内容和所有交互步骤。</p>
      <div className={styles.inspectorActions}>
        <Button variant="primary" disabled={historical || saved || saving} busy={saving} onClick={() => onSave(work.artifactId)}>
          {saved ? "已保存到我的作品" : work.workId ? "保存新版本" : "保存到我的作品"}
        </Button>
        {work.kind === "html" && !historical && <Button variant="outline" onClick={() => onEdit(work.artifactId)}>继续修改</Button>}
        {saved && <Button variant="outline" onClick={() => onEditMetadata(work.artifactId)}>编辑作品信息</Button>}
        {work.kind === "html" && !historical && <Button variant="outline" disabled={publishing || saving} busy={publishing}
          onClick={() => onPublish(work.artifactId)}>
          {published ? "更新广场发布" : saved ? "发布到教师资源广场" : "保存并发布到广场"}
        </Button>}
        {published && !historical && <Button variant="outline" onClick={() => onShare(work.artifactId)}>分享作品</Button>}
        {published && !historical && <Button variant="outline" disabled={publishing} onClick={() => onUnpublish(work.artifactId)}>撤回发布</Button>}
        {saved && <Link href="/history" className={styles.inspectorSavedLink}>在我的作品中查看</Link>}
      </div>
      <p className={styles.inspectorFuture}>{published ? "当前公开版本可供其他学习者访问。私有修改不会自动改变已发布内容。" : "公开前请先检查知识准确性、互动功能及作品中可能存在的私人信息。"}</p>
    </div>
  </aside>;
}
