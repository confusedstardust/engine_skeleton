"use client";

import { useEffect, useRef } from "react";
import { Button } from "../../components/ui/button";
import AnimationPreview from "./animation-preview";
import type { GeneratedWork } from "./generated-work-card";
import styles from "./practice.module.css";

export type WorkPreviewData = GeneratedWork & { html: string };

export default function WorkInspector({
  work, onClose, onEdit,
}: {
  work: WorkPreviewData;
  onClose: () => void;
  onEdit: (id: string) => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, work.artifactId]);

  return <aside className={styles.inspector} aria-label={`作品预览：${work.title}`}>
    <header className={styles.inspectorHeader}>
      <div><strong>{work.title}</strong><span>{work.kind === "html" ? "互动网页" : "教学动画"} · V{work.version} · 私有作品</span></div>
      <button ref={closeRef} type="button" aria-label="关闭作品预览" className={styles.inspectorClose} onClick={onClose}>×</button>
    </header>
    <div className={styles.inspectorScroll}>
      <AnimationPreview html={work.html} artifactId={work.artifactId}
        label="互动作品预览" compact />
      <p className={styles.inspectorTip}>可以直接操作预览中的控件。正式教学使用前，请检查内容和所有交互步骤。</p>
      <div className={styles.inspectorActions}>
        {work.kind === "html" && <Button variant="outline" onClick={() => onEdit(work.artifactId)}>继续修改</Button>}
        <span className={styles.inspectorFuture}>保存到我的作品、发布资源广场和分享将在作品持久化接通后启用。</span>
      </div>
    </div>
  </aside>;
}
