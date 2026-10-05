"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { withBasePath } from "../base-path";
import { getCurrentUser, jsonAuthHeaders } from "../invite-identity";
import { CreditBalance } from "../../components/credit-balance";

type Asset = {
  id: string; name: string; kind: string; source_type: string; created_at: string;
  file_id: string; revision: number; variant: string; mime_type: string; size_bytes: number;
  width_px?: number | null; height_px?: number | null; duration_ms?: number | null; url: string;
};
type Job = { id: string; status: string; has_published_build?: boolean; options?: { classroom_topic?: string }; source_material?: string };

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(withBasePath(`/api/forge${path}`), {
    ...init, credentials: "include", headers: { ...jsonAuthHeaders(), ...(init?.headers || {}), ...(init?.body ? { "Content-Type": "application/json" } : {}) },
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<T>;
}

const labels: Record<string, string> = { BACKGROUND: "场景", FIGURE: "角色", VOICE: "语音", BGM: "音乐", SFX: "音效", OTHER: "其他" };
const targets: Record<string, string> = { BACKGROUND: "background", FIGURE: "figure", BGM: "bgm" };

export default function AssetsPage() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobId, setJobId] = useState("");
  const [filter, setFilter] = useState("ALL");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");

  useEffect(() => {
    let active = true;
    getCurrentUser().then((user) => {
      if (!user) throw new Error("请先登录 NarrativeOS");
      return Promise.all([api<{ assets: Asset[] }>("/assets"), api<{ jobs: Job[] }>("/jobs")]);
    }).then(([assetData, jobData]) => {
      if (!active) return;
      setAssets(assetData.assets || []); setJobs(jobData.jobs || []);
      if (jobData.jobs?.[0]) setJobId(jobData.jobs[0].id);
    }).catch((reason) => active && setError(reason instanceof Error ? reason.message : "资产库加载失败"))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  const visible = useMemo(() => assets.filter((asset) => asset.variant === "original" && (filter === "ALL" || asset.kind === filter)), [assets, filter]);
  async function applyAsset(asset: Asset) {
    const target = targets[asset.kind];
    if (!target || !jobId) return;
    setBusy(asset.file_id); setError(""); setNotice("");
    try {
      await api(`/jobs/${jobId}/assets/from-library`, { method: "POST", body: JSON.stringify({ asset_file_id: asset.file_id, target }) });
      setNotice(`已将「${asset.name}」加入所选作品草稿`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "调用素材失败");
    } finally { setBusy(""); }
  }
  function jobName(job: Job) { return job.options?.classroom_topic || job.source_material?.split(/\r?\n/)[0]?.slice(0, 28) || job.id.slice(0, 8); }

  return <>
    <header className="top-nav"><div className="workspace-nav-leading"><Link className="brand brand-link" href="/"><div className="brand-seal"><img src={withBasePath("/icon.png")} alt="" /></div><div className="brand-copy"><span className="brand-name">临场 · 我的资产</span><span className="brand-subtitle">PERSONAL ASSET LIBRARY</span></div></Link><Link className="workspace-back" href="/"><span>返回首页</span></Link></div><nav className="nav-links"><Link href="/history">我的作品</Link><CreditBalance /><Link href="/login">账户</Link></nav></header>
    <main className="main-wrapper asset-library-wrapper">
      <section className="page-header asset-library-head"><div><p className="router-kicker">YOUR CREATIVE MEMORY</p><h1>我的资产库</h1><span>上传和生成的素材会自动保存在这里，可跨作品重复使用。</span></div><div className="asset-use-target"><label htmlFor="asset-target-job">调用到作品</label><select id="asset-target-job" value={jobId} onChange={(event) => setJobId(event.target.value)}><option value="">请选择作品</option>{jobs.map((job) => <option key={job.id} value={job.id}>{jobName(job)}</option>)}</select></div></section>
      <section className="asset-library-filters" aria-label="素材筛选">{["ALL", "BACKGROUND", "FIGURE", "VOICE", "BGM"].map((kind) => <button className={filter === kind ? "active" : ""} key={kind} onClick={() => setFilter(kind)}>{kind === "ALL" ? "全部" : labels[kind]}</button>)}</section>
      {notice ? <div className="asset-library-notice">{notice}</div> : null}{error ? <div className="history-empty error">{error}</div> : null}{loading ? <div className="history-empty">正在整理你的资产...</div> : null}
      {!loading && !error && visible.length === 0 ? <div className="history-empty"><strong>这里还没有素材</strong><span>在作品中上传或生成图片、语音和音乐后，会自动出现在这里。</span><Link className="btn primary" href="/?workspace=1">开始创作</Link></div> : null}
      <section className="asset-library-grid">{visible.map((asset) => <article className="asset-library-card" key={asset.file_id}><div className="asset-library-preview">{asset.mime_type.startsWith("image/") ? <img src={asset.url} alt={asset.name} /> : asset.mime_type.startsWith("audio/") ? <audio controls preload="none" src={asset.url} /> : <span>{labels[asset.kind] || "素材"}</span>}</div><div className="asset-library-card-body"><div><span className="asset-kind">{labels[asset.kind] || asset.kind}</span><h2>{asset.name}</h2><p>{asset.source_type === "GENERATED" ? "AI 生成" : "用户上传"} · 第 {asset.revision} 版{asset.width_px ? ` · ${asset.width_px}×${asset.height_px}` : ""}</p></div>{targets[asset.kind] ? <button className="btn primary" disabled={!jobId || busy === asset.file_id} onClick={() => applyAsset(asset)}>{busy === asset.file_id ? "正在加入..." : "用于作品"}</button> : <span className="asset-library-hint">暂不支持直接调用</span>}</div></article>)}</section>
    </main>
  </>;
}
