"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { withBasePath } from "../base-path";
import { getCurrentUser, jsonAuthHeaders } from "../invite-identity";

type Asset = { id: string; name: string; kind: string; source_type: string; created_at: string; file_id?: string | null; mime_type?: string | null; size_bytes?: number | null; width_px?: number | null; height_px?: number | null; url?: string | null };
type Cursor = { created_at: string; id: string } | null;
type AssetResponse = { items: Asset[]; next_cursor: Cursor };
const kindLabels: Record<string, string> = { BACKGROUND: "背景", FIGURE: "角色", VOICE: "语音", BGM: "音乐", SFX: "音效", OTHER: "其他" };

function formatSize(bytes?: number | null) {
  if (!bytes) return "—";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

async function fetchAssets(source: string, kind: string, cursor?: Cursor): Promise<AssetResponse> {
  const params = new URLSearchParams({ limit: "30" });
  if (source !== "ALL") params.set("source_type", source);
  if (kind !== "ALL") params.set("kind", kind);
  if (cursor) { params.set("cursor_created_at", cursor.created_at); params.set("cursor_id", cursor.id); }
  const response = await fetch(withBasePath(`/api/forge/assets?${params}`), { credentials: "include", headers: jsonAuthHeaders() });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(body?.detail || "素材库加载失败");
  }
  return response.json() as Promise<AssetResponse>;
}

export default function AssetsPage() {
  const [items, setItems] = useState<Asset[]>([]);
  const [source, setSource] = useState("ALL");
  const [kind, setKind] = useState("ALL");
  const [cursor, setCursor] = useState<Cursor>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [authMissing, setAuthMissing] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(async (append = false, next?: Cursor) => {
    if (append) setLoadingMore(true);
    else setLoading(true);
    try {
      const data = await fetchAssets(source, kind, next);
      setItems((current) => append ? [...current, ...data.items] : data.items);
      setCursor(data.next_cursor); setError("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "素材库加载失败"); }
    finally { setLoading(false); setLoadingMore(false); }
  }, [kind, source]);

  useEffect(() => {
    let active = true;
    getCurrentUser().then((user) => {
      if (!active) return;
      if (!user || user.auth_type !== "sso") { setAuthMissing(true); setLoading(false); return; }
      setAuthMissing(false); void load();
    });
    return () => { active = false; };
  }, [load]);

  return <>
    <header className="top-nav"><div className="workspace-nav-leading"><Link className="brand brand-link" href="/?workspace=1"><div className="brand-seal"><img src={withBasePath("/icon.png")} alt="" /></div><div className="brand-copy"><span className="brand-name">临场 · 素材库</span><span className="brand-subtitle">ASSET LIBRARY</span></div></Link><Link className="workspace-back" href="/?workspace=1"><span>返回工作台</span></Link></div><nav className="nav-links"><Link href="/history">我的作品</Link><Link className="nav-login" href="/login">账户</Link></nav></header>
    <main className="main-wrapper asset-library-wrapper">
      <section className="page-header asset-library-head"><div><h1>我的素材库</h1><p>AI 生成和你上传的素材统一保存到 OSS，并按账号隔离。</p></div><span>{items.length} 项已加载</span></section>
      <section className="asset-library-toolbar" aria-label="素材筛选"><div>{[["ALL","全部来源"],["GENERATED","AI 生成"],["UPLOADED","用户上传"],["IMPORTED","素材库导入"]].map(([value,label]) => <button type="button" key={value} className={source === value ? "active" : ""} onClick={() => setSource(value)}>{label}</button>)}</div><select aria-label="素材类型" value={kind} onChange={(event) => setKind(event.target.value)}><option value="ALL">全部类型</option>{Object.entries(kindLabels).map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></section>
      {authMissing ? <div className="history-empty"><strong>请先登录 NarrativeOS</strong><span>素材库仅对正式账号开放。</span><Link className="btn primary" href="/login">前往登录</Link></div> : null}
      {loading ? <div className="history-empty">正在加载素材...</div> : null}
      {error ? <div className="history-empty error"><strong>暂时无法加载素材库</strong><span>{error}</span><button className="btn outline" type="button" onClick={() => void load()}>重试</button></div> : null}
      {!loading && !error && !authMissing && items.length === 0 ? <div className="history-empty"><strong>暂无素材</strong><span>生成游戏或在素材审阅页上传文件后，素材会出现在这里。</span><Link className="btn primary" href="/?workspace=1">创建游戏</Link></div> : null}
      <section className="asset-library-grid" aria-label="素材列表">{items.map((asset) => <article className="asset-library-card" key={asset.id}><div className="asset-library-preview">{asset.mime_type?.startsWith("image/") && asset.url ? <img src={asset.url} alt={asset.name} loading="lazy" /> : <span>{["VOICE","BGM","SFX"].includes(asset.kind) ? asset.kind : "FILE"}</span>}</div><div className="asset-library-copy"><div><span className={`asset-source ${asset.source_type.toLowerCase()}`}>{asset.source_type === "GENERATED" ? "AI 生成" : asset.source_type === "UPLOADED" ? "用户上传" : "素材库"}</span><span>{kindLabels[asset.kind] || asset.kind}</span></div><h2 title={asset.name}>{asset.name}</h2><p>{asset.width_px && asset.height_px ? `${asset.width_px} × ${asset.height_px} · ` : ""}{formatSize(asset.size_bytes)}</p></div></article>)}</section>
      {cursor ? <div className="asset-library-more"><button className="btn outline" type="button" disabled={loadingMore} onClick={() => void load(true, cursor)}>{loadingMore ? "加载中..." : "加载更多"}</button></div> : null}
    </main>
  </>;
}
