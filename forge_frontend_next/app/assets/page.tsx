"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { withBasePath } from "../base-path";
import { getCurrentUser, jsonAuthHeaders } from "../invite-identity";
import { CreditBalance } from "../../components/credit-balance";

type Asset = {
  id: string; name: string; kind: string; source_type: string; created_at: string;
  file_id: string; revision: number; variant: string; mime_type: string; size_bytes: number;
  width_px?: number | null; height_px?: number | null; duration_ms?: number | null; url: string;
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(withBasePath(`/api/forge${path}`), {
    ...init, credentials: "include", headers: { ...jsonAuthHeaders(), ...(init?.headers || {}), ...(init?.body ? { "Content-Type": "application/json" } : {}) },
  });
  if (!response.ok) {
    const body = await response.text();
    try {
      const parsed = JSON.parse(body) as { detail?: string };
      throw new Error(parsed.detail || body);
    } catch (error) {
      if (error instanceof SyntaxError) throw new Error(body || `请求失败（HTTP ${response.status}）`);
      throw error;
    }
  }
  return response.json() as Promise<T>;
}

const labels: Record<string, string> = { BACKGROUND: "场景", FIGURE: "角色", VOICE: "语音", BGM: "音乐", SFX: "音效", OTHER: "其他" };

function EditIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path className="edit-frame" d="M11 4H5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2v-6" /><path className="edit-pencil" d="m13.15 5.15 5.7 5.7L9.2 20.5l-5.7 1 1-5.7 9.65-10.65Zm1.42-1.42 2.16-2.16a2 2 0 0 1 2.83 0l2.87 2.87a2 2 0 0 1 0 2.83l-2.16 2.16-5.7-5.7Z" /></svg>;
}

function TrashIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6.5 7l1 13h9l1-13M10 11v5M14 11v5" /></svg>;
}

export default function AssetsPage() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [filter, setFilter] = useState("ALL");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [editingId, setEditingId] = useState("");
  const [nameDraft, setNameDraft] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<Asset | null>(null);
  const cancelEditRef = useRef(false);

  useEffect(() => {
    let active = true;
    getCurrentUser().then((user) => {
      if (!user) throw new Error("请先登录 NarrativeOS");
      return api<{ assets: Asset[] }>("/assets");
    }).then((assetData) => {
      if (!active) return;
      setAssets(assetData.assets || []);
    }).catch((reason) => active && setError(reason instanceof Error ? reason.message : "资产库加载失败"))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  const visible = useMemo(() => assets.filter((asset) => asset.variant === "original" && (filter === "ALL" || asset.kind === filter)), [assets, filter]);
  async function saveName(asset: Asset) {
    const name = nameDraft.trim();
    if (!name || name === asset.name) {
      setNameDraft(asset.name);
      setEditingId("");
      return;
    }
    setBusy(asset.id);
    setError("");
    try {
      const value = await api<{ asset: { id: string; name: string } }>(`/assets/${asset.id}/name`, { method: "PUT", body: JSON.stringify({ name }) });
      setAssets((current) => current.map((item) => item.id === asset.id ? { ...item, name: value.asset.name } : item));
      setEditingId("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "素材改名失败");
    } finally {
      setBusy("");
    }
  }
  async function deleteAsset(asset: Asset) {
    setBusy(asset.id);
    setError("");
    try {
      await api(`/assets/${asset.id}`, { method: "DELETE" });
      setAssets((current) => current.filter((item) => item.id !== asset.id));
      setDeleteTarget(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "素材删除失败");
    } finally {
      setBusy("");
    }
  }

  return <>
    <header className="top-nav"><div className="workspace-nav-leading"><Link className="brand brand-link" href="/"><div className="brand-seal"><img src={withBasePath("/icon.png")} alt="" /></div><div className="brand-copy"><span className="brand-name">临场 · 我的资产</span><span className="brand-subtitle">PERSONAL ASSET LIBRARY</span></div></Link><Link className="workspace-back" href="/"><span>返回首页</span></Link></div><nav className="nav-links"><Link href="/history">我的作品</Link><CreditBalance /><Link href="/login">账户</Link></nav></header>
    <main className="main-wrapper asset-library-wrapper">
      <section className="page-header asset-library-head"><div><p className="router-kicker">YOUR CREATIVE MEMORY</p><h1>我的资产库</h1></div></section>
      <section className="asset-library-filters" aria-label="素材筛选">{["ALL", "BACKGROUND", "FIGURE", "VOICE", "BGM"].map((kind) => <button className={filter === kind ? "active" : ""} key={kind} onClick={() => setFilter(kind)}>{kind === "ALL" ? "全部" : labels[kind]}</button>)}</section>
      {error ? <div className="history-empty error">{error}</div> : null}{loading ? <div className="history-empty">正在整理你的资产...</div> : null}
      {!loading && !error && visible.length === 0 ? <div className="history-empty"><strong>这里还没有素材</strong><span>在作品中上传或生成图片、语音和音乐后，会自动出现在这里。</span><Link className="btn primary" href="/?workspace=1">开始创作</Link></div> : null}
      <section className="asset-library-grid">{visible.map((asset) => <article className="asset-library-card" key={asset.file_id}><div className="asset-library-preview">{asset.mime_type.startsWith("image/") ? <img src={asset.url} alt={asset.name} /> : asset.mime_type.startsWith("audio/") ? <audio controls preload="none" src={asset.url} /> : <span>{labels[asset.kind] || "素材"}</span>}</div><div className="asset-library-card-body"><div className="asset-library-card-copy"><span className="asset-kind">{labels[asset.kind] || asset.kind}</span>{editingId === asset.id ? <input className="asset-name-input" value={nameDraft} maxLength={200} autoFocus aria-label="素材名称" disabled={busy === asset.id} onChange={(event) => setNameDraft(event.target.value)} onBlur={() => { if (cancelEditRef.current) { cancelEditRef.current = false; return; } void saveName(asset); }} onKeyDown={(event) => { if (event.key === "Enter") event.currentTarget.blur(); if (event.key === "Escape") { cancelEditRef.current = true; setNameDraft(asset.name); setEditingId(""); event.currentTarget.blur(); } }} /> : <div className="asset-name-display"><h2>{asset.name}</h2><button type="button" aria-label="修改素材名称" title="修改素材名称" onClick={() => { setEditingId(asset.id); setNameDraft(asset.name); setError(""); }}><EditIcon /></button></div>}<p>{asset.source_type === "GENERATED" ? "AI 生成" : "用户上传"} · 第 {asset.revision} 版{asset.width_px ? ` · ${asset.width_px}×${asset.height_px}` : ""}</p></div><button className="asset-delete" type="button" aria-label={`删除素材 ${asset.name}`} title="删除素材" disabled={busy === asset.id} onClick={() => setDeleteTarget(asset)}><TrashIcon /></button></div></article>)}</section>
      {deleteTarget ? <div className="asset-confirm-layer" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) setDeleteTarget(null); }}><section className="asset-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="asset-delete-title"><div className="asset-confirm-icon"><TrashIcon /></div><h2 id="asset-delete-title">删除这个素材？</h2><p>“{deleteTarget.name}”将从你的资产库中移除，已发布游戏不会受到影响。</p><div className="asset-confirm-actions"><button className="btn outline" type="button" disabled={Boolean(busy)} onClick={() => setDeleteTarget(null)}>取消</button><button className="btn primary" type="button" disabled={Boolean(busy)} onClick={() => void deleteAsset(deleteTarget)}>{busy ? "正在删除…" : "确认删除"}</button></div></section></div> : null}
    </main>
  </>;
}
