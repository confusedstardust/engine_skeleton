"use client";

import { useEffect, useState } from "react";
import { withBasePath } from "../app/base-path";
import { jsonAuthHeaders } from "../app/invite-identity";
import { ConfirmDialog } from "./ui/modal";

type Publication = { published: boolean; work?: { title: string }; owner_user_id?: string };

export default function AdminGamePublication({ jobId, canPublish, blocked }: { jobId: string; canPublish: boolean; blocked: boolean }) {
  const [publication, setPublication] = useState<Publication | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [action, setAction] = useState<"POST" | "DELETE" | null>(null);
  const [revision, setRevision] = useState(0);
  const url = withBasePath(`/api/forge/admin/games/${encodeURIComponent(jobId)}/ecosystem-publication`);

  async function readResponse(response: Response): Promise<Publication> {
    const text = await response.text();
    let data;
    try { data = JSON.parse(text); }
    catch { throw new Error(`教师生态服务响应异常（HTTP ${response.status}）`); }
    if (!response.ok) throw new Error(data.detail || "教师生态操作失败");
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

  async function submit() {
    if (!action || busy) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const data = await fetch(url, { method: action, credentials: "include", headers: { ...jsonAuthHeaders(), "X-Forge-Admin-Action": "1" } }).then(readResponse);
      setPublication(previous => ({ ...previous, ...data }));
      setMessage(action === "DELETE" ? "已取消教师生态发布" : "已发布到教师生态，作品保留原作者归属");
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失败，请重新查询发布状态");
    } finally { setBusy(false); setAction(null); }
  }

  return <section className="admin-detail-configuration">
    <p>发布后，教师可以在教师生态中发现并体验这个作品。作品保留原作者及账号归属。</p>
    {loading ? <p role="status">正在查询发布状态…</p> : publication ? <>
      <dl className="admin-detail-info"><div><dt>发布状态</dt><dd>{publication.published ? "已发布到教师生态" : "尚未发布"}</dd></div>
        {publication.work?.title ? <div><dt>生态作品名称</dt><dd>{publication.work.title}</dd></div> : null}
        {publication.owner_user_id ? <div><dt>原作者账号</dt><dd>{publication.owner_user_id}</dd></div> : null}</dl>
      {!canPublish ? <p>{blocked ? "作品已下架，请先恢复作品再发布。" : "作品尚未生成可播放版本，暂时不能发布。"}</p> : null}
      <div className="admin-actions"><button className="btn primary" disabled={busy || !canPublish} onClick={() => setAction("POST")}>{publication.published ? "更新生态发布" : "发布到教师生态"}</button>
        {publication.published ? <button className="btn outline" disabled={busy} onClick={() => setAction("DELETE")}>取消生态发布</button> : null}</div>
    </> : null}
    {error ? <p className="history-empty error" role="alert">{error}</p> : null}
    {message ? <p role="status">{message}</p> : null}
    <button className="btn outline" disabled={busy || loading} onClick={() => { setMessage(""); setRevision(value => value + 1); }}>刷新发布状态</button>
    <ConfirmDialog open={action !== null} title={action === "DELETE" ? "取消教师生态发布？" : publication?.published ? "更新教师生态作品？" : "发布到教师生态？"}
      description={action === "DELETE" ? "教师生态中将不再展示此作品，原游戏保留。" : "将当前已生成的可播放作品发布到教师生态，归属原作者账号。"}
      busy={busy} onCancel={() => setAction(null)} onConfirm={() => void submit()} />
  </section>;
}
