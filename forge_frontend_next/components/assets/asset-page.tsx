"use client";
import { useToast } from "../ui/toast";
import { CollectionCard } from "@narrativeos/ui/collection-card";
import { WorkbenchHeader } from "../workbench-header";
import type { LibraryAsset as Asset } from "../../domain/assets";
import { forgeApi as api } from "../../lib/api-client";



import { useIncrementalList } from "../../hooks/use-incremental-list";
import { AssetPreview } from "./asset-preview";



import { FormSelect } from "../../components/ui/form-controls";
import { assetCategories } from "../../components/asset-categories";
import { ConfirmDialog } from "../../components/ui/modal";
import Link from "next/link";

import { useEffect, useRef, useState } from "react";

import { getCurrentUser } from "../../app/invite-identity";



const labels: Record<string, string> = { BACKGROUND: "场景", FIGURE: "角色", VOICE: "语音", BGM: "音乐", SFX: "音效", OTHER: "其他" };

function FavoriteIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 2.8 5.7 6.3.9-4.55 4.45 1.07 6.28L12 17.36l-5.62 2.97 1.07-6.28L2.9 9.6l6.3-.9L12 3Z" /></svg>;
}

function TrashIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6.5 7l1 13h9l1-13M10 11v5M14 11v5" /></svg>;
}

export default function AssetsPage({ personal = false }: { personal?: boolean }) {
  const [collection, setCollection] = useState(personal ? "uploads" : "library");
  const [favoriteIds, setFavoriteIds] = useState<string[]>([]);
  const [userId, setUserId] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [revision, setRevision] = useState(0);
  const [category, setCategory] = useState("");
  const [filter, setFilter] = useState("ALL");
  const notify = useToast();
  const [busy, setBusy] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<Asset | null>(null);
  const canManage = (asset: Asset) => personal && asset.owner_user_id === userId && asset.source_type === "UPLOADED" && asset.visibility === "PRIVATE";
  const gridRef = useRef<HTMLElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);

  const resetKey = JSON.stringify([collection, filter, category, query, revision]);
  const identityRef = useRef<{ key: string; promise: ReturnType<typeof getCurrentUser> } | null>(null);
  const list = useIncrementalList<Asset, number>({ resetKey, initialCursor: 0, keyOf: asset => asset.file_id,
    load: async (offset, signal) => {
      if (identityRef.current?.key !== resetKey) identityRef.current = { key: resetKey, promise: getCurrentUser() };
      const user = await identityRef.current.promise;
      if (signal.aborted) throw new DOMException("Aborted", "AbortError");
      if (!user) throw new Error("请先登录 NarrativeOS");
      setUserId(user.id);
      const columns = gridRef.current ? getComputedStyle(gridRef.current).gridTemplateColumns.split(" ").filter(Boolean).length : 1;
      const size = Math.min(48, Math.max(1, columns) * (offset === 0 ? 2 : 3));
      const params = new URLSearchParams({ offset: String(offset), page_size: String(size), search: query });
      params.set("exclude_voice", "true");
      if (collection === "library") params.set("source_type", "GENERATED"); else params.set("collection", collection);
      if (category) params.set("category", category);
      if (filter !== "ALL") params.set("kind", filter);
      const data = await api<{ assets: Asset[]; has_more: boolean; total: number; next_offset: number }>(`/assets?${params}`, { signal });
      if (!signal.aborted) setFavoriteIds(current => Array.from(new Set([...current, ...data.assets.filter(asset => asset.is_favorite).map(asset => asset.id)])));
      return { items: data.assets, next: data.next_offset, hasMore: data.has_more, total: data.total };
    }
  });
  const { items: assets, setItems: setAssets, loading, error: feedError, hasMore, total } = list;
  const loadNextRef = useRef(list.loadNext); loadNextRef.current = list.loadNext;
  useEffect(() => { setFavoriteIds([]); setDeleteTarget(null); }, [resetKey]);

  useEffect(() => {
    if (loading || feedError || !hasMore || !sentinelRef.current || !("IntersectionObserver" in window)) return;
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) loadNextRef.current();
    });
    observer.observe(sentinelRef.current);
    return () => observer.disconnect();
  }, [loading, feedError, hasMore]);

  const visible = assets;
  async function toggleFavorite(asset: Asset) {
    const favorite = !favoriteIds.includes(asset.id);
    setBusy(asset.id);

    try {
      await api(`/assets/${asset.id}/favorite`, { method: favorite ? "PUT" : "DELETE" });
      setFavoriteIds((current) => favorite ? [...current, asset.id] : current.filter((id) => id !== asset.id));
      notify(favorite ? "已收藏素材" : "已取消收藏", "success");
      if (collection === "favorites") setRevision((value) => value + 1);
    } catch (reason) {
      notify(reason instanceof Error ? reason.message : "收藏操作失败", "error");
    } finally { setBusy(""); }
  }
  async function deleteAsset(asset: Asset) {
    if (!canManage(asset)) return;
    setDeleteError("");
    setBusy(asset.id);

    try {
      await api(`/assets/${asset.id}`, { method: "DELETE" });
      setAssets((current) => current.filter((item) => item.id !== asset.id));
      notify("素材已删除", "success");
      setDeleteTarget(null);
      setRevision((value) => value + 1);
    } catch (reason) {
      setDeleteError(reason instanceof Error ? reason.message : "素材删除失败");
    } finally {
      setBusy("");
    }
  }

  return <>
    <WorkbenchHeader title={personal ? "我的资产" : "素材库"} subtitle="ASSET LIBRARY" />
    <main className="main-wrapper asset-library-wrapper asset-library-page">
      <section className="page-header asset-library-head"><div><p className="router-kicker">ASSET LIBRARY</p><h1>{personal ? "我的资产" : "素材库"}</h1></div></section>
      <section className="asset-library-filters" aria-label="素材来源" hidden={!personal}>{[["uploads", "我的上传"], ["favorites", "我的收藏"]].map(([value, label]) => <button key={value} className={collection === value ? "active" : ""} onClick={() => { setCollection(value); }}>{label}</button>)}</section>
      <section className="asset-library-filters" aria-label="素材筛选">{["ALL", "BACKGROUND", "FIGURE", "BGM"].map((kind) => <button className={filter === kind ? "active" : ""} key={kind} onClick={() => { setFilter(kind); setCategory(""); }}>{kind === "ALL" ? "全部" : labels[kind]}</button>)}</section>
      <form className="asset-library-search" role="search" onSubmit={(event) => { event.preventDefault(); setQuery(search.trim()); }}><FormSelect value={category} ariaLabel="素材分类" options={[{value:"",label:"全部分类"}, ...assetCategories.filter((item) => item.kinds.some(kind => kind !== "VOICE") && (filter === "ALL" || item.kinds.includes(filter)))]} onValueChange={(value) => {setCategory(value);}} /><input type="search" aria-label="搜索素材" placeholder="搜索名称、分类或标签" value={search} onChange={(event) => { const value = event.target.value; setSearch(value); if (!value) { setQuery(""); } }} /><button className="btn primary" type="submit">搜索</button></form>
      {!loading && !feedError && visible.length === 0 ? <div className="history-empty"><strong>{query ? "没有找到匹配的素材" : "这里还没有素材"}</strong>{personal ? <span>上传或收藏对应素材后，可以在作品中选用。</span> : null}<Link className="btn primary" href="/?workspace=1">开始创作</Link></div> : null}
      <section ref={gridRef} className="asset-library-grid" aria-busy={loading}>{visible.map((asset) => <CollectionCard className="asset-library-card" key={asset.file_id} menuLabel={`素材操作：${asset.name}`} actions={[
        { id: "favorite", label: favoriteIds.includes(asset.id) ? "取消收藏" : "收藏素材", disabled: busy === asset.id, onSelect: () => void toggleFavorite(asset) },
        ...(canManage(asset) ? [
          { id: "delete", label: "删除素材", destructive: true, disabled: busy === asset.id, onSelect: () => { setDeleteError(""); setDeleteTarget(asset); } },
        ] : []),
      ]}><div className="asset-library-preview" data-asset-kind={asset.kind}><AssetPreview asset={asset} fallback={labels[asset.kind] || "素材"} /></div><div className="asset-library-card-body"><div className="asset-library-card-top"><span className="asset-kind">{asset.category_label || labels[asset.kind] || asset.kind}</span><div className="asset-library-card-actions"><button className="asset-delete asset-favorite" type="button" aria-label={favoriteIds.includes(asset.id) ? "取消收藏" : "收藏素材"} aria-pressed={favoriteIds.includes(asset.id)} title={favoriteIds.includes(asset.id) ? "取消收藏" : "收藏素材"} disabled={busy === asset.id} onClick={() => void toggleFavorite(asset)}><FavoriteIcon /></button>{canManage(asset) ? <button className="asset-delete" type="button" aria-label={`删除素材 ${asset.name}`} title="删除素材" disabled={busy === asset.id} onClick={() => setDeleteTarget(asset)}><TrashIcon /></button> : null}</div></div><div className="asset-library-card-copy"><div className="asset-name-display"><h2>{asset.name}</h2></div></div></div></CollectionCard>)}</section>
      <div ref={sentinelRef} className="asset-library-feed-status" role="status" aria-live="polite">
        <span>已加载 {assets.length} / {total} 项</span>
        {loading ? <span>正在加载素材…</span> : feedError ? <><span className="error">{feedError}</span><button className="btn outline" type="button" onClick={() => loadNextRef.current()}>重试</button></> : hasMore ? <button className="btn outline" type="button" onClick={() => loadNextRef.current()}>加载更多</button> : assets.length ? <span>已加载全部素材</span> : null}
      </div>
      <ConfirmDialog error={deleteError} open={Boolean(deleteTarget)} title="删除这个素材？" description={`“${deleteTarget?.name || ""}”将从素材仓库中移除，已发布游戏不会受到影响。`} busy={Boolean(busy)} onCancel={() => setDeleteTarget(null)} onConfirm={() => { if (deleteTarget) void deleteAsset(deleteTarget); }} />
    </main>
  </>;
}

