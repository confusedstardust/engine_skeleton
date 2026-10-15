"use client";

import { ReturnLink } from "../../components/navigation-return";



import Link from "next/link";
import { AccountMenu } from "../../components/account-menu";
import { useEffect, useMemo, useState } from "react";
import { withBasePath } from "../base-path";
import { getCurrentUser, jsonAuthHeaders } from "../invite-identity";

type Job = {
  id: string;
  title?: string;
  status: string;
  phase?: string | null;
  error?: string | null;
  build_state?: string;
  has_published_build?: boolean;
  source_material?: string;
  created_at?: string;
  updated_at?: string;
  options?: {
    classroom_topic?: string;
    generation_mode?: string;
    voice_enabled?: boolean;
    generate_assets?: boolean;
    [key: string]: unknown;
  };
  artifacts?: Record<string, string>;
};

type JobsResponse = {
  jobs: Job[];
};

const statusLabels: Record<string, string> = {
  CREATED: "已创建",
  QUEUED: "排队中",
  RUNNING: "生成中",
  DONE: "已完成",
  FAILED: "失败",
  NARRATIVE_READY: "大纲完成",
  GAME_DESIGN_READY: "设计完成",
  ASSET_MANIFEST_READY: "素材规划完成",
  ASSET_GENERATION_READY: "素材完成",
  SCENES_READY: "场景完成",
  VALIDATION_PASSED: "校验通过",
};

async function api<T>(path: string): Promise<T> {
  const response = await fetch(withBasePath(`/api/forge${path}`), {
    credentials: "include",
    headers: jsonAuthHeaders(),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<T>;
}

function jobTitle(job: Job) {
  const title = String(job.title || "").trim();
  if (title) return title;
  const topic = String(job.options?.classroom_topic || "").trim();
  if (topic) return topic;
  const source = String(job.source_material || "").trim();
  const firstLine = source.split(/\r?\n/).find(Boolean);
  return firstLine?.replace(/^课堂主题[:：]\s*/, "").slice(0, 36) || "未命名游戏";
}

function formatTime(value?: string) {
  if (!value) return "未知时间";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "未知时间";
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function statusClass(status: string) {
  const normalized = status.toLowerCase();
  if (normalized.includes("failed")) return "failed";
  if (normalized === "done" || normalized.includes("passed") || normalized.includes("ready")) return "done";
  if (normalized === "running" || normalized === "queued") return "running";
  return "created";
}

export default function HistoryPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [authMissing, setAuthMissing] = useState(false);
  const [filter, setFilter] = useState<"all" | "running" | "done" | "failed">("all");

  useEffect(() => {
    let active = true;
    getCurrentUser().then((user) => {
      if (!active) return null;
      if (!user) {
        setAuthMissing(true);
        setLoading(false);
        return null;
      }
      return api<JobsResponse>("/jobs");
    })
      .then((data) => {
        if (!active || !data) return;
        setJobs(data.jobs || []);
        setError("");
      })
      .catch((err) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : "我的作品加载失败");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const filteredJobs = useMemo(() => {
    if (filter === "all") return jobs;
    return jobs.filter((job) => statusClass(job.status) === filter);
  }, [filter, jobs]);

  const counts = useMemo(
    () => ({
      all: jobs.length,
      running: jobs.filter((job) => statusClass(job.status) === "running").length,
      done: jobs.filter((job) => statusClass(job.status) === "done").length,
      failed: jobs.filter((job) => statusClass(job.status) === "failed").length,
    }),
    [jobs],
  );

  return (
    <>
      <header className="top-nav">
        <div className="workspace-nav-leading">
          <Link className="brand brand-link" href="/?workspace=1">
            <div className="brand-seal" aria-hidden="true">
              <img src={withBasePath("/icon.png")} alt="" />
            </div>
            <div className="brand-copy">
              <span className="brand-name">临场 · 我的作品</span>
              <span className="brand-subtitle">MY WORKS</span>
            </div>
          </Link>

        </div>
        <nav className="nav-links" aria-label="记录导航"><ReturnLink />
          <Link href="/?workspace=1">新建任务</Link>

          <AccountMenu className="nav-login" includeAdmin />
        </nav>
      </header>

      <main className="main-wrapper history-wrapper">
        <section className="page-header history-head" aria-labelledby="history-title">
          <h1 id="history-title">我的作品</h1>
        </section>

        <section className="history-toolbar" aria-label="记录筛选">
          {(["all", "running", "done", "failed"] as const).map((item) => (
            <button
              className={filter === item ? "active" : ""}
              key={item}
              type="button"
              onClick={() => setFilter(item)}
            >
              {item === "all" ? "全部" : item === "running" ? "生成中" : item === "done" ? "已完成" : "失败"}
              <span>{counts[item]}</span>
            </button>
          ))}
        </section>

        {loading ? <div className="history-empty">正在加载我的作品...</div> : null}
        {authMissing ? (
          <div className="history-empty">
            <strong>请先登录 NarrativeOS</strong>
            <span>作品会按登录账号隔离。</span>
            <Link className="btn primary" href="/login">前往登录</Link>
          </div>
        ) : null}
        {error ? <div className="history-empty error">{error}</div> : null}
        {!loading && !authMissing && !error && filteredJobs.length === 0 ? (
          <div className="history-empty">
            <strong>暂无记录</strong>
            <span>新建任务后，我的作品会出现在这里。</span>
            <Link className="btn primary" href="/?workspace=1">创建新任务</Link>
          </div>
        ) : null}

        <section className="history-list" aria-label="生成任务列表">
          {filteredJobs.map((job) => (
            <article className="history-row" key={job.id}>
              <div className="history-row-main">
                <div className="history-title-line">
                  <h2>{jobTitle(job)}</h2>
                  <span className={`history-status ${statusClass(job.status)}`}>
                    {job.build_state === "STALE" ? "有未发布修改" : job.build_state === "FAILED" && job.has_published_build ? "新版本失败" : statusLabels[job.status] || job.status}
                  </span>
                </div>
                <div className="history-meta">
                  <span>更新 {formatTime(job.updated_at || job.created_at)}</span>
                  {job.phase ? <span>{job.phase}</span> : null}
                </div>
                {job.error ? <p className="history-error">{job.error}</p> : null}
              </div>
              <div className="history-actions">
                <Link className="btn outline" href={`/jobs/${job.id}`}>{job.has_published_build === true || (job.has_published_build === undefined && job.status === "DONE") ? "管理作品" : job.status === "RUNNING" || job.status === "QUEUED" ? "查看进度" : "继续编辑"}</Link>
                {job.has_published_build === true || (job.has_published_build === undefined && job.status === "DONE") ? (
                  <a className="btn primary" href={withBasePath(`/play/${job.id}/`)} target="_blank" rel="noreferrer">
                    打开游戏
                  </a>
                ) : (
                  <button className="btn primary" type="button" disabled>未完成</button>
                )}
              </div>
            </article>
          ))}
        </section>
      </main>
    </>
  );
}
