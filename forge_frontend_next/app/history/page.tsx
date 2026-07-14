"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { withBasePath } from "../base-path";
import { getStoredInviteCode, jsonInviteHeaders } from "../invite-identity";

type Job = {
  id: string;
  status: string;
  phase?: string | null;
  error?: string | null;
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
    headers: jsonInviteHeaders(),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<T>;
}

function compactId(id: string) {
  return `${id.slice(0, 8)}...${id.slice(-4)}`;
}

function jobTitle(job: Job) {
  const topic = String(job.options?.classroom_topic || "").trim();
  if (topic) return topic;
  const source = String(job.source_material || "").trim();
  const firstLine = source.split(/\r?\n/).find(Boolean);
  return firstLine?.replace(/^课堂主题[:：]\s*/, "").slice(0, 36) || `任务 ${compactId(job.id)}`;
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
  const [inviteMissing, setInviteMissing] = useState(false);
  const [filter, setFilter] = useState<"all" | "running" | "done" | "failed">("all");

  useEffect(() => {
    let active = true;
    if (!getStoredInviteCode()) {
      setInviteMissing(true);
      setLoading(false);
      return () => {
        active = false;
      };
    }
    api<JobsResponse>("/jobs")
      .then((data) => {
        if (!active) return;
        setJobs(data.jobs || []);
        setError("");
      })
      .catch((err) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : "生成记录加载失败");
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
        <Link className="brand brand-link" href="/">
          <div className="brand-seal" aria-hidden="true">
            <img src={withBasePath("/icon.png")} alt="" />
          </div>
          <div className="brand-copy">
            <span className="brand-name">临场 · 生成记录</span>
            <span className="brand-subtitle">GENERATION HISTORY</span>
          </div>
        </Link>
        <nav className="nav-links" aria-label="记录导航">
          <Link href="/">新建任务</Link>
          <Link className="nav-login" href="/login">邀请码</Link>
        </nav>
      </header>

      <main className="main-wrapper history-wrapper">
        <section className="page-header history-head" aria-labelledby="history-title">
          <h1 id="history-title">生成记录</h1>
          <p>这里只显示当前邀请码身份下创建的任务，不会混入其他邀请码的生成记录。</p>
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

        {loading ? <div className="history-empty">正在加载生成记录...</div> : null}
        {inviteMissing ? (
          <div className="history-empty">
            <strong>请先输入邀请码</strong>
            <span>生成记录和游戏库会按邀请码身份隔离。</span>
            <Link className="btn primary" href="/login">填写邀请码</Link>
          </div>
        ) : null}
        {error ? <div className="history-empty error">{error}</div> : null}
        {!loading && !inviteMissing && !error && filteredJobs.length === 0 ? (
          <div className="history-empty">
            <strong>暂无记录</strong>
            <span>新建任务后，生成记录会出现在这里。</span>
            <Link className="btn primary" href="/">创建新任务</Link>
          </div>
        ) : null}

        <section className="history-list" aria-label="生成任务列表">
          {filteredJobs.map((job) => (
            <article className="history-row" key={job.id}>
              <div className="history-row-main">
                <div className="history-title-line">
                  <h2>{jobTitle(job)}</h2>
                  <span className={`history-status ${statusClass(job.status)}`}>
                    {statusLabels[job.status] || job.status}
                  </span>
                </div>
                <div className="history-meta">
                  <span>任务 {compactId(job.id)}</span>
                  <span>更新 {formatTime(job.updated_at || job.created_at)}</span>
                  <span>{job.phase || "等待开始"}</span>
                </div>
                {job.error ? <p className="history-error">{job.error}</p> : null}
              </div>
              <div className="history-actions">
                <Link className="btn outline" href={`/jobs/${job.id}`}>继续编辑</Link>
                {job.status === "DONE" ? (
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
