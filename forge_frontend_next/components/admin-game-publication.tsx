"use client";
import { useToast } from "./ui/toast";
import { adminApi } from "../lib/api-client";

import { useEffect, useState } from "react";

type Publication = { published: boolean; work?: { title: string }; owner_user_id?: string };

export default function AdminGamePublication({ jobId, canPublish, blocked, plazaPublished, isPracticeTool }: { jobId: string; canPublish: boolean; blocked: boolean; plazaPublished: boolean; isPracticeTool: boolean }) {
  const notify = useToast();
  const [publication, setPublication] = useState<Publication | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [practiceBusy, setPracticeBusy] = useState(false);
  const [practiceTool, setPracticeTool] = useState(isPracticeTool);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const url = `/games/${encodeURIComponent(jobId)}/ecosystem-publication`;

  useEffect(() => {
    if (revision === 0) return;
    const controller = new AbortController();
    setLoading(true); setError(""); setPublication(null);
    adminApi<Publication>(url, { signal: controller.signal }).then(data => { if (!controller.signal.aborted) setPublication(data); })
      .catch(e => { if (!controller.signal.aborted) setError(e.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [url, revision]);

  async function togglePublication() {
    if (!publication || busy || practiceBusy) return;
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

  async function togglePracticeTool() {
    setPracticeBusy(true);
    try {
      const data = await adminApi<{ is_practice_tool: boolean }>(
        `/games/${encodeURIComponent(jobId)}/practice-tool`,
        { method: "PUT", body: JSON.stringify({ enabled: !practiceTool }) },
      );
      setPracticeTool(data.is_practice_tool);
      notify(data.is_practice_tool ? "已设为讲练工具" : "已移出讲练工具", "success");
    } catch (e) {
      notify(e instanceof Error ? e.message : "讲练工具设置失败", "error");
    } finally {
      setPracticeBusy(false);
    }
  }

  const practiceAction = (publication?.published ?? plazaPublished) && (
    <button className="btn outline" type="button" disabled={busy || practiceBusy} onClick={() => void togglePracticeTool()}>
      {practiceBusy ? "正在保存…" : practiceTool ? "移出讲练工具" : "设为讲练工具"}
    </button>
  );

  if (revision === 0) return <>{practiceAction}<button className="btn outline" type="button" onClick={() => setRevision(1)}>查询广场发布状态</button></>;
  if (loading) return <>{practiceAction}<button className="btn outline" type="button" disabled>正在查询教师资源广场…</button></>;
  if (!publication) return <>{practiceAction}<p role="alert">{error}</p><button className="btn outline" type="button" title={error} onClick={() => setRevision(value => value + 1)}>重试教师资源广场状态</button></>;
  const disabled = busy || practiceBusy || (!publication.published && !canPublish);
  const unavailableReason = blocked ? "作品已下架，请先恢复作品再发布" : "作品尚未生成可播放版本，暂时不能发布";
  return <>{practiceAction}<button
    className={`btn ${publication.published ? "outline" : "primary"}`}
    type="button"
    disabled={disabled}
    title={error || ((!publication.published && !canPublish) ? unavailableReason : undefined)}
    aria-label={error ? `${publication.published ? "取消发布教师资源广场" : "发布到教师资源广场"}，上次操作失败：${error}` : undefined}
    onClick={() => void togglePublication()}
  >
    {busy ? "正在处理…" : publication.published ? "取消发布教师资源广场" : "发布到教师资源广场"}
  </button></>;
}
