"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { Button } from "../../components/ui/button";
import AnimationPreview from "./animation-preview";
import type { GeneratedWork } from "./generated-work-card";
import styles from "./practice.module.css";

export type WorkPreviewData = GeneratedWork & {
  html: string;
  workId?: string;
  savedArtifactId?: string;
  currentVersionId?: string;
  expectedParentArtifactId?: string;
};

export default function WorkInspector({
  work, onClose, onEdit, onSave, saving = false,
}: {
  work: WorkPreviewData;
  onClose: () => void;
  onEdit: (id: string) => void;
  onSave: (id: string) => void;
  saving?: boolean;
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
  return <aside className={styles.inspector} aria-label={`作品预览：${work.title}`}>
    <header className={styles.inspectorHeader}>
      <div><strong>{work.title}</strong><span>{work.kind === "html" ? "互动网页" : "教学动画"} · V{work.version} · {saved ? "已保存" : "尚未保存"}</span></div>
      <button ref={closeRef} type="button" aria-label="关闭作品预览" className={styles.inspectorClose} onClick={onClose}>×</button>
    </header>
    <div className={styles.inspectorScroll}>
      <AnimationPreview html={work.html} artifactId={work.artifactId} label="互动作品预览" compact storedAssetsBase={work.workId && work.currentVersionId && work.savedArtifactId === work.artifactId ? `/api/forge/works/${work.workId}/assets/${work.currentVersionId}` : undefined} />
      <p className={styles.inspectorTip}>可直接操作预览中的控件。正式教学使用前，请核对内容和所有交互步骤。</p>
      <div className={styles.inspectorActions}>
        <Button variant="primary" disabled={saved || saving} busy={saving} onClick={() => onSave(work.artifactId)}>
          {saved ? "已保存到我的作品" : work.workId ? "保存新版本" : "保存到我的作品"}
        </Button>
        {work.kind === "html" && <Button variant="outline" onClick={() => onEdit(work.artifactId)}>继续修改</Button>}
        {saved && <Link href="/history" className={styles.inspectorSavedLink}>在我的作品中查看</Link>}
      </div>
      <p className={styles.inspectorFuture}>保存后会进入长期作品库。广场发布和公开分享将在发布接口接通后开放。</p>
    </div>
  </aside>;
}
