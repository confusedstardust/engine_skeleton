"use client";
import { useToast } from "../../components/ui/toast";
import { PublishedFlowModal } from "../../components/published-flow-modal";
import { ConfirmDialog, ModalFrame, ModalBody, useConfirmation } from "../../components/ui/modal";
import { CollectionCard } from "@narrativeos/ui/collection-card";
import { WorkbenchHeader } from "../../components/workbench-header";
import { forgeApi as api } from "../../lib/api-client";
import type { Job } from "../../domain/jobs";







import Link from "next/link";

import { useEffect, useMemo, useRef, useState } from "react";
import { withBasePath } from "../base-path";
import { getCurrentUser } from "../invite-identity";

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

type Publication = { published: boolean };
function playable(job: Job) { return job.has_published_build ?? job.status === "DONE"; }
function building(job: Job) { return job.status === "RUNNING" || job.status === "QUEUED" || job.build_state === "BUILDING"; }
function editorHref(job: Job) { return `/jobs/${job.id}${playable(job) && !building(job) ? '?edit=1' : ''}`; }
export default function HistoryPage() {
  const confirm = useConfirmation();
  const [publications, setPublications] = useState<Record<string, Publication>>({});
  const requests = useRef(new Set<string>());
  const publicationVersions = useRef<Record<string, number>>({});
  const mutationLock = useRef<string | null>(null);
  const [actionBusy, setActionBusy] = useState("");
  const notify = useToast();
  const [flowJob, setFlowJob] = useState<Job | null>(null);
  const [deleteJob, setDeleteJob] = useState<Job | null>(null);
  const [deleteError, setDeleteError] = useState("");
  async function removeJob() {
    if (!deleteJob || mutationLock.current || building(deleteJob)) return;
    mutationLock.current = deleteJob.id;
    setActionBusy(deleteJob.id); setDeleteError("");
    try {
      await api(`/jobs/${deleteJob.id}`, { method: "DELETE" });
      publicationVersions.current[deleteJob.id] = (publicationVersions.current[deleteJob.id] || 0) + 1;
      setJobs(current => current.filter(job => job.id !== deleteJob.id));
      setDeleteJob(null);
      notify("任务已删除。", "success");
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : "删除失败，请重试。");
    } finally { mutationLock.current = null; setActionBusy(""); }
  }
  const [renameJob, setRenameJob] = useState<Job | null>(null);
  const [titleDraft, setTitleDraft] = useState("");
  const [titleBusy, setTitleBusy] = useState(false);
  const [titleError, setTitleError] = useState("");
  function beginRename(job: Job) {
    setRenameJob(job); setTitleDraft(jobTitle(job)); setTitleError("");
  }
  async function saveTitle() {
    if (!renameJob || titleBusy || !titleDraft.trim()) return;
    setTitleBusy(true); setTitleError("");
    try {
      const result = await api<{ job: Job }>(`/jobs/${renameJob.id}/title`, { method: "PUT", body: JSON.stringify({ title: titleDraft.trim() }) });
      setJobs(current => current.map(job => job.id === renameJob.id ? { ...job, ...result.job } : job));
      setRenameJob(null);
    } catch (error) { setTitleError(error instanceof Error ? error.message : "作品重命名失败，请重试。"); }
    finally { setTitleBusy(false); }
  }
  async function loadPublication(job: Job) {
    if (!playable(job) || requests.current.has(job.id) || mutationLock.current === job.id) return;
    requests.current.add(job.id);
    const version = (publicationVersions.current[job.id] || 0) + 1;
    publicationVersions.current[job.id] = version;
    try {
      const value = await api<Publication>(`/jobs/${job.id}/ecosystem-publication`);
      if (publicationVersions.current[job.id] === version) setPublications(current => ({ ...current, [job.id]: value }));
    } catch (error) {
      if (publicationVersions.current[job.id] === version) { notify(error instanceof Error ? error.message : "发布状态读取失败，请重新打开菜单重试。", "error"); }
    } finally { requests.current.delete(job.id); }
  }
  async function changePublication(job: Job, remove = false) {
    if (mutationLock.current || building(job)) return;
    // Reserve the operation before awaiting confirmation to prevent duplicate submissions.
    mutationLock.current = job.id;
    setActionBusy(job.id);
    try {
      if (remove && !(await confirm('确定从教师资源广场中取消发布吗？游戏本身不会被删除。'))) return;
      publicationVersions.current[job.id] = (publicationVersions.current[job.id] || 0) + 1;
      const value = await api<Publication>(`/jobs/${job.id}/ecosystem-publication`, {
        method: remove ? "DELETE" : "POST", ...(remove ? {} : { body: JSON.stringify({}) }),
      });
      setPublications(current => ({ ...current, [job.id]: value }));
      notify(remove ? "已取消生态发布。" : "已发布到教师资源广场。", "success");
    } catch (error) {
      notify(error instanceof Error ? error.message : "操作失败，请重试。", "error");
    } finally { mutationLock.current = null; setActionBusy(""); }
  }
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
      <ConfirmDialog open={Boolean(deleteJob)} title="删除任务" description="确定删除这个任务吗？删除后原游戏链接将无法访问，已发布到教师广场的作品会同时下架。" error={deleteError} busy={Boolean(actionBusy)} onCancel={() => setDeleteJob(null)} onConfirm={() => void removeJob()} />
      <WorkbenchHeader title="临场 · 我的作品" subtitle="MY WORKS" brandHref="/?workspace=1" label="记录导航" accountClassName="nav-login">
<Link href="/?workspace=1">新建任务</Link>
</WorkbenchHeader>

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
            <CollectionCard className="history-row" key={job.id} menuLabel={`作品操作：${jobTitle(job)}`}
              onContextMenu={() => void loadPublication(job)}
              onClickCapture={event => { if ((event.target as HTMLElement).closest('.nos-card-more')) void loadPublication(job); }}
              onKeyDown={event => { if (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) void loadPublication(job); }}
              actions={[
                ...(playable(job) ? [{ id: "play", label: "开始游戏", href: withBasePath(`/play/${job.id}/`), newTab: true }] : []),
                { id: "edit", label: building(job) ? "查看进度" : playable(job) ? "编辑" : "继续编辑", href: withBasePath(editorHref(job)) },
                { id: "rename", label: "重命名", disabled: building(job) || titleBusy, onSelect: () => beginRename(job) },
                ...(playable(job) ? [
                  { id: "publish", label: !publications[job.id] ? "读取发布状态…" : publications[job.id].published ? "更新发布" : "发布", disabled: !publications[job.id] || building(job) || Boolean(actionBusy), onSelect: () => void changePublication(job) },
                  ...(publications[job.id]?.published ? [{ id: "unpublish", label: "取消生态发布", disabled: building(job) || Boolean(actionBusy), onSelect: () => void changePublication(job, true) }] : []),
                  { id: "practice", label: "打开习题", href: withBasePath(`/practice/${job.id}`) },
                  { id: "flow", label: "流程图", onSelect: () => setFlowJob(job) },
                ] : []),
                { id: "delete", label: "删除任务", destructive: true, disabled: building(job) || Boolean(actionBusy), onSelect: () => { setDeleteError(""); setDeleteJob(job); } },
              ]}>
              <div className="history-cover">{playable(job) ? <><span aria-hidden="true">封面暂不可用</span><img src={withBasePath(`/play/${job.id}/cover?revision=${job.published_revision ?? 0}`)} alt={`${jobTitle(job)}封面`} loading="lazy" onLoad={event => { event.currentTarget.style.visibility = "visible"; }} onError={event => { event.currentTarget.style.visibility = "hidden"; }} /></> : <span>封面待生成</span>}</div>
              <div className="history-row-main">
                <div className="history-title-line">
                  <h2><Link className="history-card-link" href={editorHref(job)} aria-label={`打开作品：${jobTitle(job)}`}>{jobTitle(job)}</Link></h2>
                  <button className="history-title-edit" type="button" aria-label={`重命名作品：${jobTitle(job)}`} title="重命名作品" disabled={building(job) || titleBusy} onClick={() => beginRename(job)}>
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M11 4H5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2v-6" /><path d="m16 5 3 3M9 15l4-1 8-8a2.12 2.12 0 0 0-3-3l-8 8-1 4Z" /></svg>
                  </button>
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
            </CollectionCard>
          ))}
        </section>
        {renameJob && <ModalFrame title="重命名作品" onClose={() => setRenameJob(null)} busy={titleBusy}>
          <div className="history-rename-overlay"><ModalBody><section className="history-rename-dialog">
            <h2>重命名作品</h2>
            <form onSubmit={event => { event.preventDefault(); void saveTitle(); }}>
              <label htmlFor="history-title-draft">作品名称</label>
              <input id="history-title-draft" autoFocus value={titleDraft} maxLength={160} disabled={titleBusy} onChange={event => setTitleDraft(event.target.value)} />
              {titleError && <p role="alert">{titleError}</p>}
              <div className="asset-confirm-actions"><button className="btn outline" type="button" disabled={titleBusy} onClick={() => setRenameJob(null)}>取消</button><button className="btn primary" type="submit" disabled={titleBusy || !titleDraft.trim()}>保存</button></div>
            </form>
          </section></ModalBody></div>
        </ModalFrame>}
        {flowJob && <PublishedFlowModal job={flowJob} onClose={() => setFlowJob(null)} />}
      </main>
    </>
  );
}
