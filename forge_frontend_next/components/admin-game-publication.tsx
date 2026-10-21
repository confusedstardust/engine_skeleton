"use client";
import { useToast } from "./ui/toast";
import { adminApi } from "../lib/api-client";

import { useEffect, useState } from "react";

type Publication = { published: boolean; work?: { title: string }; owner_user_id?: string };

export default function AdminGamePublication({ jobId, canPublish, blocked }: { jobId: string; canPublish: boolean; blocked: boolean }) {
  const notify = useToast();
  const [publication, setPublication] = useState<Publication | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const url = `/games/${encodeURIComponent(jobId)}/ecosystem-publication`;

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(""); setPublication(null);
    adminApi<Publication>(url, { signal: controller.signal }).then(data => { if (!controller.signal.aborted) setPublication(data); })
      .catch(e => { if (!controller.signal.aborted) setError(e.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [url, revision]);

  async function togglePublication() {
    if (!publication || busy) return;
    const method = publication.published ? "DELETE" : "POST";
    setBusy(true); setError("");
    try {
      const data = await adminApi<Publication>(url, { method });
      setPublication(previous => ({ ...previous, ...data }));
      notify(data.published ? "已发布到教师资源广场" : "已取消生态发布", "success");
    } catch (e) {
      notify(e instanceof Error ? e.message : "操作失败，请重新查询发布状态", "error");
    } finally { setBusy(false); }
  }

  if (loading) return <button className="btn outline" type="button" disabled>正在查询教师资源广场…</button>;
  if (!publication) return <><p role="alert">{error}</p><button className="btn outline" type="button" title={error} onClick={() => setRevision(value => value + 1)}>重试教师资源广场状态</button></>;
  const disabled = busy || (!publication.published && !canPublish);
  const unavailableReason = blocked ? "作品已下架，请先恢复作品再发布" : "作品尚未生成可播放版本，暂时不能发布";
  return <button
    className={`btn ${publication.published ? "outline" : "primary"}`}
    type="button"
    disabled={disabled}
    title={error || ((!publication.published && !canPublish) ? unavailableReason : undefined)}
    aria-label={error ? `${publication.published ? "取消发布教师资源广场" : "发布到教师资源广场"}，上次操作失败：${error}` : undefined}
    onClick={() => void togglePublication()}
  >
    {busy ? "正在处理…" : publication.published ? "取消发布教师资源广场" : "发布到教师资源广场"}
  </button>;
}
