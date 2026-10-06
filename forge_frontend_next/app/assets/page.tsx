"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { withBasePath } from "../base-path";
import { getCurrentUser, jsonAuthHeaders } from "../invite-identity";
import { CreditBalance } from "../../components/credit-balance";

type Asset = {
  is_favorite?: boolean; owner_user_id: string; id: string; name: string; kind: string; source_type: string; created_at: string;
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

function FavoriteIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 2.8 5.7 6.3.9-4.55 4.45 1.07 6.28L12 17.36l-5.62 2.97 1.07-6.28L2.9 9.6l6.3-.9L12 3Z" /></svg>;
}

function TrashIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6.5 7l1 13h9l1-13M10 11v5M14 11v5" /></svg>;
}

export default function AssetsPage() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [collection, setCollection] = useState("library");
  const [favoriteIds, setFavoriteIds] = useState<string[]>([]);
  const [userId, setUserId] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [revision, setRevision] = useState(0);
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
    setLoading(true);
    setError("");
    getCurrentUser().then((user) => {
      if (!user) throw new Error("请先登录 NarrativeOS");
      if (!active) return null;
      setUserId(user.id);
      const params = new URLSearchParams({ page: String(page), page_size: "12", search: query });
      if (collection === "library") params.set("source_type", "GENERATED");
      else params.set("collection", collection);
      if (filter !== "ALL") params.set("kind", filter);
      return api<{ assets: Asset[]; has_more: boolean }>(`/assets?${params}`);
    }).then((data) => {
      if (!active || !data) return;
      if (!data.assets.length && page > 1) { setPage(page - 1); return; }
      setAssets(data.assets);
      setFavoriteIds(data.assets.filter((asset) => asset.is_favorite).map((asset) => asset.id));
      setHasMore(data.has_more);
    }).catch((reason) => active && setError(reason instanceof Error ? reason.message : "素材仓库加载失败"))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [collection, filter, query, page, revision]);

  const visible = loading ? [] : assets;
  async function toggleFavorite(asset: Asset) {
    const favorite = !favoriteIds.includes(asset.id);
    setBusy(asset.id);
    setError("");
    try {
      await api(`/assets/${asset.id}/favorite`, { method: favorite ? "PUT" : "DELETE" });
      setFavoriteIds((current) => favorite ? [...current, asset.id] : current.filter((id) => id !== asset.id));
      if (collection === "favorites") setRevision((value) => value + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "收藏操作失败");
    } finally { setBusy(""); }
  }
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
      setRevision((value) => value + 1);
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
      setRevision((value) => value + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "素材删除失败");
    } finally {
      setBusy("");
    }
  }

  return <>
    <header className="top-nav"><div className="workspace-nav-leading"><Link className="brand brand-link" href="/"><div className="brand-seal"><img src={withBasePath("/icon.png")} alt="" /></div><div className="brand-copy"><span className="brand-name">素材仓库</span><span className="brand-subtitle">ASSET LIBRARY</span></div></Link><Link className="workspace-back" href="/"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 18-6-6 6-6" /></svg><span>返回首页</span></Link></div><nav className="nav-links"><Link href="/history">我的作品</Link><CreditBalance /><Link href="/login">账户</Link></nav></header>
    <main className="main-wrapper asset-library-wrapper">
      <section className="page-header asset-library-head"><div><p className="router-kicker">ASSET LIBRARY</p><h1>素材仓库</h1></div></section>
      <section className="asset-library-filters" aria-label="素材来源">{[["library", "素材库"], ["uploads", "我的上传"], ["favorites", "我的收藏"]].map(([value, label]) => <button key={value} className={collection === value ? "active" : ""} onClick={() => { setCollection(value); setPage(1); }}>{label}</button>)}</section>
      <section className="asset-library-filters" aria-label="素材筛选">{["ALL", "BACKGROUND", "FIGURE", "VOICE", "BGM"].map((kind) => <button className={filter === kind ? "active" : ""} key={kind} onClick={() => { setFilter(kind); setPage(1); }}>{kind === "ALL" ? "全部" : labels[kind]}</button>)}</section>
      <form className="asset-library-search" role="search" onSubmit={(event) => { event.preventDefault(); setQuery(search.trim()); setPage(1); }}><input type="search" aria-label="搜索素材名称" placeholder="搜索素材名称" value={search} onChange={(event) => setSearch(event.target.value)} /><button className="btn primary" type="submit">搜索</button>{query ? <button className="btn outline" type="button" onClick={() => { setSearch(""); setQuery(""); setPage(1); }}>清除</button> : null}</form>
      {error ? <div className="history-empty error">{error}</div> : null}{loading ? <div className="history-empty">正在加载素材...</div> : null}
      {!loading && !error && visible.length === 0 ? <div className="history-empty"><strong>{query ? "没有找到匹配的素材" : "这里还没有素材"}</strong><span>上传或收藏对应素材后，可以在作品中选用。</span><Link className="btn primary" href="/?workspace=1">开始创作</Link></div> : null}
      <section className="asset-library-grid">{visible.map((asset) => <article className="asset-library-card" key={asset.file_id}><div className="asset-library-preview">{asset.mime_type.startsWith("image/") ? <img src={asset.url} alt={asset.name} /> : asset.mime_type.startsWith("audio/") ? <audio controls preload="none" src={asset.url} /> : <span>{labels[asset.kind] || "素材"}</span>}</div><div className="asset-library-card-body"><div className="asset-library-card-top"><span className="asset-kind">{labels[asset.kind] || asset.kind}</span><div className="asset-library-card-actions"><button className="asset-delete asset-favorite" type="button" aria-label={favoriteIds.includes(asset.id) ? "取消收藏" : "收藏素材"} aria-pressed={favoriteIds.includes(asset.id)} title={favoriteIds.includes(asset.id) ? "取消收藏" : "收藏素材"} disabled={busy === asset.id} onClick={() => void toggleFavorite(asset)}><FavoriteIcon /></button>{asset.owner_user_id === userId ? <button className="asset-delete" type="button" aria-label={`删除素材 ${asset.name}`} title="删除素材" disabled={busy === asset.id} onClick={() => setDeleteTarget(asset)}><TrashIcon /></button> : null}</div></div><div className="asset-library-card-copy">{editingId === asset.id ? <input className="asset-name-input" value={nameDraft} maxLength={200} autoFocus aria-label="素材名称" disabled={busy === asset.id} onChange={(event) => setNameDraft(event.target.value)} onBlur={() => { if (cancelEditRef.current) { cancelEditRef.current = false; return; } void saveName(asset); }} onKeyDown={(event) => { if (event.key === "Enter") event.currentTarget.blur(); if (event.key === "Escape") { cancelEditRef.current = true; setNameDraft(asset.name); setEditingId(""); event.currentTarget.blur(); } }} /> : <div className="asset-name-display"><h2>{asset.name}</h2>{asset.owner_user_id === userId ? <button type="button" aria-label="修改素材名称" title="修改素材名称" onClick={() => { setEditingId(asset.id); setNameDraft(asset.name); setError(""); }}><EditIcon /></button> : null}</div>}<p>{asset.source_type === "GENERATED" ? "AI 生成" : "用户上传"} · 第 {asset.revision} 版{asset.width_px ? ` · ${asset.width_px}×${asset.height_px}` : ""}</p></div></div></article>)}</section>
      {!error ? <nav className="asset-library-pagination" aria-label="素材分页"><button className="btn outline" disabled={loading || page === 1} onClick={() => setPage((value) => value - 1)}>上一页</button><span aria-live="polite">第 {page} 页 · 每页 12 项</span><button className="btn outline" disabled={loading || !hasMore} onClick={() => setPage((value) => value + 1)}>下一页</button></nav> : null}
      {deleteTarget ? <div className="asset-confirm-layer" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) setDeleteTarget(null); }}><section className="asset-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="asset-delete-title"><div className="asset-confirm-icon"><TrashIcon /></div><h2 id="asset-delete-title">删除这个素材？</h2><p>“{deleteTarget.name}”将从你的资产库中移除，已发布游戏不会受到影响。</p><div className="asset-confirm-actions"><button className="btn outline" type="button" disabled={Boolean(busy)} onClick={() => setDeleteTarget(null)}>取消</button><button className="btn primary" type="button" disabled={Boolean(busy)} onClick={() => void deleteAsset(deleteTarget)}>{busy ? "正在删除…" : "确认删除"}</button></div></section></div> : null}
    </main>
  </>;
}
