"use client";

import { useState } from "react";
import { Button } from "../../components/ui/button";
import { ModalBody, ModalFrame } from "../../components/ui/modal";
import type { PublicationForm } from "../../lib/work-api";
import type { WorkPreviewData } from "./work-inspector";
import { withBasePath } from "../base-path";
import styles from "./practice.module.css";

export default function WorkPublishDialog({
  work, onClose, onSubmit, busy, error, mode = "publish",
}: {
  work: WorkPreviewData;
  onClose: () => void;
  onSubmit: (payload: PublicationForm) => void;
  busy: boolean;
  error?: string;
  mode?: "publish" | "edit";
}) {
  const [title, setTitle] = useState(work.title);
  const [summary, setSummary] = useState(work.summary || "");
  const [subject, setSubject] = useState(work.subject || "");
  const [grade, setGrade] = useState(work.grade || "");
  const [tags, setTags] = useState((work.tags || []).join("，"));
  const [coverVariant, setCoverVariant] = useState<"preview" | "mobile">(work.coverVariant || "preview");
  const editing = mode === "edit";
  return <ModalFrame title={editing ? "编辑作品信息" : "发布到教师资源广场"} onClose={onClose} busy={busy}>
    <div className={styles.publishOverlay}><ModalBody>
      <section className={styles.publishDialog}>
        <h2>{editing ? "编辑作品信息" : "发布到教师资源广场"}</h2>
        <p>{editing ? "完善作品标题、简介、学科、学段和标签。更新资料不会自动修改已公开的版本。" :
          "发布后，其他教师和学习者可公开访问这件作品。发布的是当前确认的版本，后续私有修改不会自动更新公开内容。"}</p>
        {error && <p className={styles.publishError} role="alert">{error}</p>}
        <form onSubmit={event => {
          event.preventDefault();
          if (!title.trim() || busy) return;
          onSubmit({
            title: title.trim(), summary: summary.trim(),
            subject: subject.trim() || null, grade: grade.trim() || null,
            tags: tags.split(/[,，]/).map(t => t.trim()).filter(Boolean).slice(0, 8),
            ...(editing ? { cover_variant: coverVariant } : {}),
          });
        }}>
          <label>作品名称<input maxLength={160} required value={title} disabled={busy}
            onChange={e => setTitle(e.target.value)} /></label>
          <label>作品简介<textarea maxLength={2000} rows={3} value={summary} disabled={busy}
            placeholder="让其他老师了解这件作品如何帮助学生学习" onChange={e => setSummary(e.target.value)} /></label>
          <div className={styles.publishFields}>
            <label>学科<input maxLength={80} value={subject} disabled={busy} placeholder="如：数学" onChange={e => setSubject(e.target.value)} /></label>
            <label>学段<input maxLength={80} value={grade} disabled={busy} placeholder="如：高中" onChange={e => setGrade(e.target.value)} /></label>
          </div>
          <label>标签<input value={tags} disabled={busy} placeholder="用逗号分隔，例如：函数、可视化、探究"
            onChange={e => setTags(e.target.value)} /></label>
          {editing && work.workId && work.currentVersionId && <fieldset className={styles.coverPicker}>
            <legend>作品封面</legend>
            <div className={styles.coverOptions}>{(["preview", "mobile"] as const).map(variant => (
              <label key={variant}>
                <input type="radio" name="work-cover" value={variant}
                  checked={coverVariant === variant} disabled={busy}
                  onChange={() => setCoverVariant(variant)} />
                <img alt={variant === "preview" ? "桌面检查截图" : "手机检查截图"}
                  src={withBasePath(`/api/forge/works/${work.workId}/assets/${work.currentVersionId}/${variant}.png`)} />
                <span>{variant === "preview" ? "桌面截图" : "手机截图"}</span>
              </label>
            ))}</div>
          </fieldset>}
          <div className={styles.publishFooter}>
            <Button variant="outline" disabled={busy} onClick={onClose}>取消</Button>
            <Button type="submit" variant="primary" busy={busy} disabled={busy || !title.trim()}>{editing ? "保存作品信息" : "确认发布"}</Button>
          </div>
        </form>
      </section>
    </ModalBody></div>
  </ModalFrame>;
}
