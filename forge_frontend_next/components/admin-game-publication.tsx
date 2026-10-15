"use client";

import { useEffect, useState } from "react";
import { withBasePath } from "../app/base-path";
import { jsonAuthHeaders } from "../app/invite-identity";

type Publication = { published: boolean; work?: { title: string }; owner_user_id?: string };

export default function AdminGamePublication({ jobId, canPublish, blocked }: { jobId: string; canPublish: boolean; blocked: boolean }) {
  const [publication, setPublication] = useState<Publication | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const url = withBasePath(`/api/forge/admin/games/${encodeURIComponent(jobId)}/ecosystem-publication`);

  async function readResponse(response: Response): Promise<Publication> {
    const text = await response.text();
    let data;
    try { data = JSON.parse(text); }
    catch { throw new Error(`教师资源广场服务响应异常（HTTP ${response.status}）`); }
    if (!response.ok) throw new Error(data.detail || "教师资源广场操作失败");
    return data;
  }

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(""); setPublication(null);
    fetch(url, { credentials: "include", headers: jsonAuthHeaders(), signal: controller.signal })
      .then(readResponse).then(data => { if (!controller.signal.aborted) setPublication(data); })
      .catch(e => { if (!controller.signal.aborted) setError(e.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [url, revision]);

  async function togglePublication() {
    if (!publication || busy) return;
    const method = publication.published ? "DELETE" : "POST";
    setBusy(true); setError("");
    try {
      const data = await fetch(url, { method, credentials: "include", headers: { ...jsonAuthHeaders(), "X-Forge-Admin-Action": "1" } }).then(readResponse);
      setPublication(previous => ({ ...previous, ...data }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失败，请重新查询发布状态");
    } finally { setBusy(false); }
  }

  if (loading) return <button className="btn outline" type="button" disabled>正在查询教师资源广场…</button>;
  if (!publication) return <button className="btn outline" type="button" title={error} onClick={() => setRevision(value => value + 1)}>重试教师资源广场状态</button>;
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
