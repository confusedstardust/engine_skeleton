'use client';

import { useEffect, useRef, useState } from 'react';
import AdminHtmlResources, { type HtmlResourceListControls, type HtmlResource } from './admin-html-resources';
import AdminGamePublication from './admin-game-publication';
import { adminApi } from '../lib/api-client';
import { Button } from './ui/button';
import { DataTable } from './ui/table';
import { Pagination } from './ui/pagination';
import { InlineFeedback } from './ui/feedback';
import { EmptyState, LoadingState } from './ui/state';
import styles from './admin-html-resources.module.css';

export type TeachingGame = { id: string; name?: string; owner_user_id?: string; owner_email?: string; status?: string; phase?: string; blocked: boolean; plaza_published: boolean; is_practice_tool: boolean; created_at: string };
type GamePage = { items: TeachingGame[]; total: number; total_pages: number };
type Actions = { onGameDetail: (game: TeachingGame) => void; onGameBlock: (game: TeachingGame) => void };
type Row = { kind: 'html'; id: string; created: string; value: HtmlResource } | { kind: 'game'; id: string; created: string; value: TeachingGame };
const states: Record<string,string> = { SUCCEEDED:'生成完成', CREATED:'待生成', RUNNING:'生成中', FAILED:'生成失败', CANCELLED:'已取消', saved:'待发布', publishing:'发布待确认', published:'已发布', archived:'已下架' };

export default function AdminTeachingResources({ revision, ...actions }: Actions & { revision: number }) {
  return <AdminHtmlResources renderList={html => <TeachingResourceList refreshKey={`${revision}:${html.revision}`} html={html} {...actions} />} />;
}

function TeachingResourceList({ html, onGameDetail, onGameBlock, refreshKey }: Actions & { html: HtmlResourceListControls; refreshKey: string }) {
  const [type, setType] = useState('all');
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [games, setGames] = useState<TeachingGame[]>([]);
  const [gameTotal, setGameTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const cache = useRef(new Map<string, GamePage>());

  useEffect(() => {
    if (type === 'html') return;
    const controller = new AbortController();
    setLoading(true); setError('');
    (async () => {
      const prefix: TeachingGame[] = [];
      let total = 0;
      let totalPages = 1;
      // A mixed page can consume at most `page` game pages. Cache the prefix so
      // next/previous never skip games when HTML resources are interleaved.
      for (let current = 1; current <= page && current <= totalPages; current++) {
        const key = `${refreshKey}:${query}:${current}:${retry}`;
        let result = cache.current.get(key);
        if (!result) {
          result = await adminApi<GamePage>(`/games?${new URLSearchParams({ page: String(current), search: query })}`, { signal: controller.signal });
          if (controller.signal.aborted) return;
          cache.current.set(key, result);
        }
        prefix.push(...result.items); total = result.total; totalPages = result.total_pages;
      }
      if (!controller.signal.aborted) { setGames(prefix); setGameTotal(total); }
    })().catch(reason => { if (!controller.signal.aborted) { setError(reason instanceof Error ? reason.message : '游戏列表加载失败'); setGames([]); setGameTotal(0); } })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [page, query, type, retry, refreshKey]);

  const matchingHtml = type === 'game' ? [] : html.items.filter(item => [item.id, item.payload.title, item.payload.summary, item.payload.subject, ...item.payload.tags].filter(Boolean).join(' ').toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  const rows: Row[] = [
    ...matchingHtml.map(value => ({ kind: 'html' as const, id: value.id, created: value.created_at || '', value })),
    ...(type === 'html' ? [] : games.map(value => ({ kind: 'game' as const, id: value.id, created: value.created_at, value }))),
  ].sort((a,b) => createdTime(b.created) - createdTime(a.created) || a.id.localeCompare(b.id) || a.kind.localeCompare(b.kind));
  const total = matchingHtml.length + (type === 'html' ? 0 : gameTotal);
  const totalPages = Math.max(1, Math.ceil(total / 20));
  const safePage = Math.min(page, totalPages);
  const pending = (type !== 'html' && loading) || (type !== 'game' && html.loading);
  const visible = rows.slice((safePage - 1) * 20, safePage * 20);

  return <>
    <div className={styles.resourceToolbar}>
      <div className={styles.typeFilters} role="group" aria-label="教学资源类型">{[['all','全部'],['html','HTML资源'],['game','游戏']].map(([value,label]) => <Button key={value} aria-pressed={type === value} variant={type === value ? 'primary' : 'outline'} onClick={() => { setType(value); setPage(1); }}>{label}</Button>)}</div>
      <form className={styles.resourceSearch} onSubmit={event => { event.preventDefault(); setQuery(search.trim()); setPage(1); }}><input type="search" aria-label="搜索教学资源" placeholder="搜索标题、资源 ID 或游戏作者" value={search} onChange={event => { setSearch(event.target.value); if (!event.target.value) { setQuery(''); setPage(1); } }} /><Button type="submit">搜索</Button></form>
    </div>
    {type !== 'game' && html.error && <InlineFeedback>{html.error}</InlineFeedback>}
    {type !== 'html' && error && <InlineFeedback>{error}<Button onClick={() => setRetry(value => value + 1)}>重试游戏列表</Button></InlineFeedback>}
    {pending ? <LoadingState>正在加载教学资源…</LoadingState> : <div className={`${styles.table} ${styles.teachingTable}`}><DataTable className="admin-table"><thead><tr><th>资源 · 点击查看</th><th>类型</th><th>分类 / 归属用户</th><th>状态</th><th>操作</th></tr></thead><tbody>
      {visible.map(row => row.kind === 'html' ? <HtmlRow key={`html:${row.id}`} item={row.value} controls={html} /> : <tr key={`game:${row.id}`}>
        <td><button className={styles.resourceButton} onClick={() => onGameDetail(row.value)} aria-label={`查看游戏：${row.value.name || row.id}`}><span><strong>{row.value.name || row.id}</strong><small>{row.id}</small><em>查看游戏详情 ↗</em></span></button></td>
        <td><span className={styles.typeBadge}>游戏</span></td><td>{row.value.owner_email || row.value.owner_user_id || '—'}</td><td>{row.value.blocked ? '已下架' : states[row.value.status || ''] || row.value.status || '—'}{row.value.phase && <small>{row.value.phase}</small>}</td>
        <td><div className="admin-actions"><AdminGamePublication jobId={row.id} canPublish={row.value.status === 'SUCCEEDED' && !row.value.blocked} blocked={row.value.blocked} plazaPublished={row.value.plaza_published === true} isPracticeTool={row.value.is_practice_tool === true}/><Button onClick={() => onGameBlock(row.value)}>{row.value.blocked ? '恢复' : '下架'}</Button></div></td>
      </tr>)}
    </tbody></DataTable>{!visible.length && <EmptyState>没有匹配的教学资源</EmptyState>}</div>}
    <Pagination className="asset-library-pagination admin-pagination" page={safePage} hasMore={safePage < totalPages} onPageChange={setPage} disabled={pending} summary={`共 ${total} 项 · 第 ${safePage} / ${totalPages} 页`} ariaLabel="教学资源分页" />
  </>;
}

function createdTime(value: string) {
  // Database timestamps are UTC but may omit the timezone suffix.
  return Date.parse(/(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}Z`) || 0;
}

function HtmlRow({ item, controls }: { item: HtmlResource; controls: HtmlResourceListControls }) {
  return <tr><td><button className={styles.resourceButton} disabled={controls.busy} onClick={() => controls.onEdit(item)} aria-label={`编辑资源：${item.payload.title}`}>
    {item.payload.coverUrl ? <img className={styles.coverThumb} src={item.payload.coverUrl} alt="" loading="lazy"/> : <span className={styles.noCover}>暂无封面</span>}
    <span><strong>{item.payload.title}</strong><small>{item.id}</small><em>编辑资源 ↗</em></span></button>
    {['pending','generating'].includes(item.cover_status || '') && <small role="status">封面生成中…</small>}
    {(item.cover_error || item.metadata_sync_error) && <small className={styles.coverError}>{item.metadata_sync_error || item.cover_error}</small>}</td>
    <td><span className={styles.typeBadge}>HTML资源</span></td><td>{[...new Set([item.payload.subject,...item.payload.tags])].join(' · ')}</td>
    <td>{states[item.state] || item.state}{item.payload.featured && <small className={styles.featuredBadge}>精选</small>}</td>
    <td><div className="admin-actions"><Button disabled={controls.busy} onClick={() => controls.onFeature(item)}>{item.payload.featured ? '取消精选' : '设为精选'}</Button>{item.state === 'published' && <Button disabled={controls.busy || controls.loading} onClick={() => controls.onPracticeTool(item)}>{item.is_practice_tool ? '移出讲练工具' : '设为讲练工具'}</Button>}{['published','publishing'].includes(item.state) && <a className="btn outline" href={item.payload.playUrl} target="_blank" rel="noopener noreferrer">体验资源 ↗</a>}<Button disabled={controls.busy} onClick={() => controls.onPublication(item)}>{item.state === 'published' ? '下架' : '重试发布'}</Button></div></td>
  </tr>;
}
