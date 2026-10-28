"use client";
import { Pagination } from "../../components/ui/pagination";
import { WorkbenchHeader } from "../../components/workbench-header";
import { adminApi as api } from "../../lib/api-client";







import AdminCommunity from "../../components/admin-community";
import PaymentTestPanel from "../../components/payment-test-panel";
import AdminUserDetail from "../../components/admin-user-detail";
import AdminAssetUpload from "../../components/admin-asset-upload";
import AdminGamePublication from "../../components/admin-game-publication";
import * as Popover from "@radix-ui/react-popover";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import * as Tabs from "@radix-ui/react-tabs";
import * as Dialog from "../../components/ui/dialog";
import { ConfirmDialog } from "../../components/ui/modal";
import { withBasePath } from "../base-path";

type Item = { id: string; name?: string; nickname?: string; email?: string; kind?: string; status?: string; owner_user_id?: string; owner_email?: string; phase?: string; blocked: boolean; created_at: string; url?: string };
type GameDetail = Item & { source_material: string; progress_percent: number; draft_revision: number; published_revision: number; build_state: string; options: Record<string,unknown>; error_code?: string; error_message?: string; updated_at: string; scene_count: number; image_count: number; can_preview: boolean };
const statusLabels: Record<string,string> = {CREATED:"待生成",RUNNING:"生成中",SUCCEEDED:"生成完成",FAILED:"生成失败",CANCELLED:"已取消",ACTIVE:"正常",BLOCKED:"已停用",DELETED:"已删除"};
const optionLabels: Record<string,string> = {grade:"适用年级",duration:"游戏时长",difficulty:"学习难度",text_model:"文本模型",image_model:"图像模型",generate_tts:"生成语音",student_goal:"学生学习目标",teacher_goal:"教学目标",voice_enabled:"角色配音",narrative_mode:"叙事模式",classroom_topic:"课堂主题",generate_assets:"生成图片",generation_mode:"生成模式",output_packages:"输出内容",tts_scope:"配音范围",tts_max_total_lines:"配音句数上限",tts_max_lines_per_scene:"每场景配音上限",allow_missing_assets:"允许素材缺失"};
const AdminDashboard = dynamic(()=>import("../../components/admin-dashboard"), {ssr:false});
const inputKeys: Record<string,string> = {"课堂主题":"classroom_topic","适用年级":"grade","学习难度":"difficulty","教学目标":"teacher_goal","学生学习目标":"student_goal","叙事模式":"narrative_mode"};
function savedInputs(detail:GameDetail) {
  const rows=detail.source_material.split("\n").filter(line=>line.trim()).map(line=>{const match=line.match(/^([^：:]+)[：:](.*)$/);if(!match)return {label:"",value:line};const key=inputKeys[match[1]];return {label:match[1],value:String((key&&detail.options?.[key])||match[2].trim()||"—")};});
  for(const key of ["grade","difficulty","teacher_goal","student_goal"]) if(detail.options?.[key]&&!rows.some(row=>inputKeys[row.label]===key))rows.push({label:optionLabels[key],value:String(detail.options[key])});
  return rows;
}
const resources = [{value:"dashboard",label:"看板"},{value:"games",label:"游戏"},{value:"assets",label:"素材"},{value:"users",label:"用户"},{value:"community",label:"公告与问答"},{value:"payment-test",label:"支付测试"}];
function FilterIcon() {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 5h16l-6 7v6l-4 2v-8L4 5Z"/></svg>;
}


export default function AdminPage() {
  const [allowed,setAllowed] = useState(false);
  const [username,setUsername] = useState("");
  const [password,setPassword] = useState("");
  const [resource,setResource] = useState("dashboard");
  const [assetKind,setAssetKind] = useState("");
  const [ownerSearch,setOwnerSearch] = useState("");
  const [ownerQuery,setOwnerQuery] = useState("");
  const [assetStatus,setAssetStatus] = useState("");
  const [ownerFilterOpen,setOwnerFilterOpen] = useState(false);
  const [statusFilterOpen,setStatusFilterOpen] = useState(false);
  const [items,setItems] = useState<Item[]>([]);
  const [search,setSearch] = useState("");
  const [query,setQuery] = useState("");
  const [page,setPage] = useState(1);
  const [hasMore,setHasMore] = useState(false);
  const [total,setTotal] = useState(0);
  const [totalPages,setTotalPages] = useState(1);
  const [jumpPage,setJumpPage] = useState("1");
  const [loading,setLoading] = useState(false);
  const [error,setError] = useState("");
  const [revision,setRevision] = useState(0);
  const [busy,setBusy] = useState(false);
  const [target,setTarget] = useState<Item|null>(null);
  const [editing,setEditing] = useState("");
  const [name,setName] = useState("");
  const [userDetailId,setUserDetailId] = useState<string|null>(null);
  const [detailOpen,setDetailOpen] = useState(false);
  const [detail,setDetail] = useState<GameDetail|null>(null);
  const [detailLoading,setDetailLoading] = useState(false);
  const [detailError,setDetailError] = useState("");
  async function showDetail(item: Item) {
    setDetailOpen(true);setDetail(null);setDetailLoading(true);setDetailError("");
    try {const data=await api<{game:GameDetail}>(`/games/${encodeURIComponent(item.id)}`);setDetail(data.game);}
    catch(e){setDetailError(e instanceof Error?e.message:"详情加载失败");}
    finally{setDetailLoading(false);}
  }
  useEffect(() => { api<{admin:boolean}>("/me").then(() => setAllowed(true)).catch(() => {}); },[]);
  async function login(event: React.FormEvent) {
    event.preventDefault();setBusy(true);setError("");
    try {await api("/login",{method:"POST",body:JSON.stringify({username,password})});setPassword("");setAllowed(true);}
    catch(e){setError(e instanceof Error?e.message:"登录失败");}
    finally{setBusy(false);}
  }
  useEffect(() => {
    if (!allowed || (resource === "dashboard" || resource === "payment-test" || resource === "community")) return;
    let active=true;
    setLoading(true); setError("");
    api<{items:Item[];has_more:boolean;page:number;total:number;total_pages:number;applied_filters?:{owner_query:string;asset_status:string}}>(`/${resource}?${new URLSearchParams({page:String(page),search:query,asset_kind:resource==="assets"?assetKind:"",owner_query:resource==="assets"?ownerQuery:"",asset_status:resource==="assets"?assetStatus:""})}`)
      .then((data) => {if(active){if(resource==="assets"&&(ownerQuery||assetStatus)&&(data.applied_filters?.owner_query!==ownerQuery||data.applied_filters?.asset_status!==assetStatus))throw new Error("后端尚未加载筛选功能，请更新或重启后端服务");setItems(data.items);setHasMore(data.has_more);setTotal(data.total);setTotalPages(data.total_pages);setPage(data.page);setJumpPage(String(data.page));}})
      .catch((e) => {if(active){setError(e.message);setItems([]);setHasMore(false);setTotal(0);setTotalPages(1);}}).finally(() => {if(active)setLoading(false);});
    return () => {active=false;};
  },[allowed,resource,page,query,revision,assetKind,ownerQuery,assetStatus]);
  async function change(item: Item, action: string) {
    setBusy(true);setError("");
    try {
      await api(`/${resource}/${encodeURIComponent(item.id)}`,{method:"PATCH",body:JSON.stringify({action,name})});
      setTarget(null);setEditing("");setRevision((v)=>v+1);
    } catch(e) {setError(e instanceof Error?e.message:"操作失败");}
    finally {setBusy(false);}
  }
  const title = (item:Item) => item.name || item.nickname || item.email || item.id;
  const pageNumbers = Array.from(new Set([1, ...Array.from({length:5},(_,i)=>page+i-2).filter(n=>n>=1&&n<=totalPages), totalPages])).sort((a,b)=>a-b);
  return <>
    <WorkbenchHeader title="平台管理" subtitle="ADMINISTRATION" afterAccount={<> {allowed?<button className="btn outline" onClick={()=>{void api('/logout',{method:'POST'}).then(()=>{setAllowed(false);setItems([]);}).catch(e=>setError(e.message));}}>退出管理</button>:null} </>} />
    <main className="main-wrapper asset-library-wrapper admin-page"><section className="page-header"><h1>平台管理</h1>{allowed ? <p>版本 1.2.6</p> : null}</section>
      {error ? <div className="history-empty error" role="alert">{error}</div>:null}
      {!allowed?<form className="admin-login" onSubmit={login}><h2>管理员登录</h2><label>账号<input autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} required/></label><label>密码<input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required/></label><button className="btn primary" disabled={busy}>{busy?"正在登录…":"登录"}</button></form>:null}
      {allowed ? <Tabs.Root value={resource} onValueChange={(value)=>{setResource(value);setPage(1);setSearch("");setQuery("");setEditing("");setAssetKind("");setOwnerSearch("");setOwnerQuery("");setAssetStatus("");}}>
        <Tabs.List className="asset-library-filters" aria-label="管理对象">{resources.map((r)=><Tabs.Trigger className={resource===r.value?"active":""} value={r.value} key={r.value}>{r.label}</Tabs.Trigger>)}</Tabs.List>
        {resource==="assets"?<><div className="asset-library-filters" role="group" aria-label="素材类型">{[["","全部"],["BACKGROUND","场景"],["FIGURE","角色"],["VOICE","语音"],["BGM","音乐"]].map(([value,label])=><button type="button" key={value} className={assetKind===value?"active":""} aria-pressed={assetKind===value} onClick={()=>{setAssetKind(value);setPage(1);}}>{label}</button>)}</div><AdminAssetUpload onUploaded={()=>setRevision(v=>v+1)}/></>:null}
        {resource!=="dashboard" && resource!=="payment-test" && resource!=="community" ? <form className="asset-library-search" onSubmit={(e)=>{e.preventDefault();setQuery(search.trim());setPage(1);setRevision(v=>v+1);}}><input type="search" value={search} placeholder={resource==="games"?"搜索作品、用户邮箱或 ID":"搜索名称、邮箱或 ID"} aria-label="搜索管理对象" onChange={(e)=>{setSearch(e.target.value);if(!e.target.value){setQuery("");setPage(1);}}}/><button className="btn primary">搜索</button></form> : null}
        <Tabs.Content className="admin-tab-panel" value={resource}>
          {resource==="community"?<AdminCommunity/>:resource==="dashboard"?<AdminDashboard/>:resource==="payment-test"?<PaymentTestPanel embedded/>:<>
          {loading?<div className="history-empty">正在加载…</div>:<div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>{resource==="users"?"用户":"名称 / ID"}</th><th>{resource==="assets"?<Popover.Root open={ownerFilterOpen} onOpenChange={value=>{setOwnerFilterOpen(value);if(value)setOwnerSearch(ownerQuery);}}><Popover.Trigger asChild><button type="button" className={`admin-column-filter ${ownerQuery?"is-filtered":""}`} aria-label="筛选归属用户" aria-haspopup="dialog">归属用户 <FilterIcon/>{ownerQuery?<small>{ownerQuery}</small>:null}</button></Popover.Trigger><Popover.Portal><Popover.Content className="admin-filter-popover" sideOffset={8} align="start" collisionPadding={12} aria-label="归属用户筛选"><form onSubmit={e=>{e.preventDefault();setOwnerQuery(ownerSearch.trim());setPage(1);setOwnerFilterOpen(false);}}><label htmlFor="admin-owner-filter">归属用户</label><input id="admin-owner-filter" type="search" value={ownerSearch} placeholder="输入邮箱、昵称或用户 ID" onChange={e=>setOwnerSearch(e.target.value)}/><div className="admin-actions"><button className="btn outline" type="button" onClick={()=>{setOwnerSearch("");setOwnerQuery("");setPage(1);setOwnerFilterOpen(false);}}>清除筛选</button><button className="btn primary" type="submit">应用</button></div></form></Popover.Content></Popover.Portal></Popover.Root>:resource==="users"?"邮箱":"归属用户"}</th><th>{resource==="assets"?<Popover.Root open={statusFilterOpen} onOpenChange={setStatusFilterOpen}><Popover.Trigger asChild><button type="button" className={`admin-column-filter ${assetStatus?"is-filtered":""}`} aria-label="筛选素材状态" aria-haspopup="dialog">状态 <FilterIcon/>{assetStatus?<small>{statusLabels[assetStatus]}</small>:null}</button></Popover.Trigger><Popover.Portal><Popover.Content className="admin-filter-popover admin-status-filter" sideOffset={8} align="start" collisionPadding={12} aria-label="素材状态筛选">{[["","全部状态"],["ACTIVE","正常"],["BLOCKED","已停用"],["DELETED","已删除"]].map(([value,label])=><button type="button" key={value} className={assetStatus===value?"is-selected":""} aria-pressed={assetStatus===value} onClick={()=>{setAssetStatus(value);setPage(1);setStatusFilterOpen(false);}}>{label}<span aria-hidden="true">{assetStatus===value?"✓":""}</span></button>)}</Popover.Content></Popover.Portal></Popover.Root>:"状态"}</th><th>操作</th></tr></thead><tbody>{items.map((item)=><tr key={item.id}><td>{editing===item.id?<form onSubmit={(e)=>{e.preventDefault();void change(item,"rename");}}><input aria-label="修改名称" maxLength={resource==="users"?191:200} value={name} onChange={(e)=>setName(e.target.value)} autoFocus/><button className="btn outline" disabled={busy}>保存</button><button className="btn outline" type="button" onClick={()=>setEditing("")}>取消</button></form>:<>{item.url?<img className="admin-thumb" src={item.url} alt="" loading="lazy" decoding="async"/>:null}{resource==="users"?<button className="admin-user-name" onClick={()=>setUserDetailId(item.id)}>{title(item)}</button>:<strong>{title(item)}</strong>}<small>{item.id}</small></>}</td><td>{item.email || item.owner_email || (item.owner_user_id==="platform-public-assets"?"平台素材库":item.owner_user_id) || "—"}</td><td>{item.blocked?(resource==="games"?"已下架":"已停用"):(statusLabels[item.status||""]||item.status||"正常")}{item.phase?<small>{item.phase}</small>:null}</td><td><div className="admin-actions">{resource==="users"?<button className="btn outline" onClick={()=>setUserDetailId(item.id)}>查看详情</button>:null}{resource==="games"?<button className="btn outline" onClick={()=>void showDetail(item)}>查看详情</button>:null}{resource==="games"?<AdminGamePublication jobId={item.id} canPublish={item.status==="SUCCEEDED"&&!item.blocked} blocked={item.blocked}/>:null}{resource!=="games"?<button className="btn outline" disabled={busy} onClick={()=>{setEditing(item.id);setName(item.name||item.nickname||"");}}>改名</button>:null}<button className="btn outline" disabled={busy||item.status==="DELETED"} onClick={()=>setTarget(item)}>{item.blocked?"恢复":resource==="games"?"下架":resource==="users"?"禁用":"停用"}</button></div></td></tr>)}</tbody></table>{!items.length?<div className="history-empty">没有匹配记录</div>:null}</div>}
          <Pagination className="asset-library-pagination admin-pagination" buttonClassName="btn outline" ariaLabel="管理列表分页" layout="summary-first"
            page={page} hasMore={hasMore} disabled={loading || Boolean(error)} onPageChange={setPage}
            summary={`共 ${total} 项 · 第 ${page} / ${totalPages} 页`}
            trailing={<form className="admin-page-jump" onSubmit={e=>{e.preventDefault();const n=Number(jumpPage);if(Number.isInteger(n)&&n>=1&&n<=totalPages)setPage(n);}}>
              <label>跳至 <input type="number" aria-label="跳转页码" min={1} max={totalPages} step={1} required value={jumpPage} onChange={e=>setJumpPage(e.target.value)} disabled={loading||!!error}/> 页</label>
              <button className="btn outline" disabled={loading||!!error}>跳转</button>
            </form>}>
            {pageNumbers.map((n,i)=><span className="admin-page-choice" key={n}>{i>0&&n>pageNumbers[i-1]+1?<span aria-hidden="true">…</span>:null}<button className={`btn ${n===page?"primary":"outline"}`} aria-label={`第 ${n} 页`} aria-current={n===page?"page":undefined} disabled={loading||!!error} onClick={()=>setPage(n)}>{n}</button></span>)}
          </Pagination>
          </>}
        </Tabs.Content>
      </Tabs.Root>:null}
      {userDetailId?<AdminUserDetail key={userDetailId} userId={userDetailId} onClose={()=>setUserDetailId(null)}/>:null}
      <ConfirmDialog open={Boolean(target)} title={target?.blocked?"恢复此记录？":resource==="games"?"下架这个游戏？":"停用此记录？"} description={`“${target?title(target):""}”：${resource==="games"?"下架只禁止本平台播放，不删除游戏、不改变生成状态，作者仍可编辑；恢复后重新开放。":resource==="users"?"禁用后不能使用本平台，统一登录账号保留。":"停用后无法从素材库选用，已发布作品的文件保留。"}`} busy={busy} onCancel={()=>setTarget(null)} onConfirm={()=>{if(target)void change(target,target.blocked?"restore":"block");}}/>
      <Dialog.Root open={detailOpen} onOpenChange={setDetailOpen}>
        <Dialog.Surface overlayClassName="radix-confirm-overlay" className="admin-detail" aria-describedby={undefined}>
            <div className="admin-detail-heading"><Dialog.Title>游戏详情</Dialog.Title><div className="admin-actions">{detail?.can_preview?<a className="btn primary" href={withBasePath(`/play/${detail.id}/`)} target="_blank" rel="noopener noreferrer">预览游戏</a>:null}<Dialog.Close className="admin-detail-close" aria-label="关闭详情">×</Dialog.Close></div></div>
            {detailLoading?<p>正在加载…</p>:detailError?<p role="alert">{detailError}</p>:detail?<>
              <section className="admin-detail-configuration"><h3>生成配置</h3><dl className="admin-detail-info">{["generation_mode","narrative_mode","duration","text_model","image_model","generate_assets","voice_enabled","output_packages"].filter(key=>detail.options?.[key]!==undefined).map(key=><div key={key}><dt>{optionLabels[key]}</dt><dd>{typeof detail.options[key]==="boolean"?(detail.options[key]?"开启":"关闭"):Array.isArray(detail.options[key])?(detail.options[key] as string[]).join("、"):String(detail.options[key])}</dd></div>)}</dl></section><div className="admin-detail-overview"><section className="admin-detail-input"><h3>用户填写内容</h3><dl className="admin-detail-source">{savedInputs(detail).map((row,index)=><div key={index} className={row.label?undefined:"admin-detail-source-text"}>{row.label?<dt>{row.label}</dt>:null}<dd>{row.value}</dd></div>)}</dl></section><section className="admin-detail-meta" aria-label="作品信息">
              <div className="admin-detail-status"><span>{statusLabels[detail.status||""]||detail.status} · {detail.progress_percent}%</span><span>{detail.blocked?"已下架":"未限制访问"}</span><span>{detail.scene_count} 个场景 · {detail.image_count} 张图片</span></div>
              <dl className="admin-detail-info">
                <div><dt>作品 ID</dt><dd>{detail.id}</dd></div><div><dt>归属用户</dt><dd>{detail.owner_user_id}</dd></div>
                <div><dt>版本</dt><dd>草稿 {detail.draft_revision} · 已发布 {detail.published_revision}</dd></div><div><dt>生成阶段</dt><dd>{detail.phase||"—"}</dd></div>
                <div><dt>创建时间</dt><dd>{new Date(detail.created_at).toLocaleString()}</dd></div><div><dt>更新时间</dt><dd>{new Date(detail.updated_at).toLocaleString()}</dd></div>
              </dl></section></div>
              {detail.error_message?<p className="history-empty error">{detail.error_message}</p>:null}
              <details className="admin-detail-options"><summary>全部参数</summary><dl className="admin-detail-info">{Object.entries(detail.options||{}).map(([key,value])=><div key={key}><dt>{optionLabels[key]||key}</dt><dd>{typeof value==="boolean"?(value?"是":"否"):Array.isArray(value)?value.join("、"):typeof value==="object"?JSON.stringify(value):String(value??"—")}</dd></div>)}</dl></details>
              {!detail.can_preview?<p className="admin-detail-note">{detail.blocked?"作品已下架，恢复后可预览。":"作品尚未生成可预览内容。"}</p>:null}
            </>:null}
          </Dialog.Surface>
      </Dialog.Root>
    </main>
  </>;
}
