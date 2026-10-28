"use client";
import { Button } from '../../components/ui/button';
import { ImagePreview } from "../../components/ui/image-preview";
import { useToast } from "../../components/ui/toast";
import { EditCoverDialog } from "../../components/edit-cover-dialog";
import { PublishedFlowModal } from "../../components/published-flow-modal";
import { ConfirmDialog, ModalFrame, ModalBody, useConfirmation } from "../../components/ui/modal";
import { CollectionCard } from "@narrativeos/ui/collection-card";
import { WorkbenchHeader } from "../../components/workbench-header";
import { forgeApi as api } from "../../lib/api-client";
import type { Job } from "../../domain/jobs";
import { useWorkActions, workTitle as jobTitle, workIsPlayable as playable, workIsBuilding as building } from "../../hooks/use-work-actions";







import Link from "next/link";

import { useEffect, useMemo, useState } from "react";
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

function editorHref(job: Job) { return `/jobs/${job.id}${playable(job) && !building(job) ? '?edit=1' : ''}`; }
export default function HistoryPage() {
  const confirm = useConfirmation();
  const notify = useToast();
  const actions = useWorkActions({ confirm, notify });
  const { publications, loadPublication, changePublication } = actions;
  const actionBusy = actions.busy?.jobId || '';
  const [coverJob, setCoverJob] = useState<Job | null>(null);
  const [flowJob, setFlowJob] = useState<Job | null>(null);
  const [deleteJob, setDeleteJob] = useState<Job | null>(null);
  const deleteError = deleteJob ? actions.errors[`${deleteJob.id}:delete`] || '' : '';
  async function removeJob() {
    if (!deleteJob) return;
    const deleted = await actions.remove(deleteJob);
    if (deleted) {
      setJobs(current => current.filter(job => job.id !== deleteJob.id));
      setDeleteJob(null);
    }
  }
  const [renameJob, setRenameJob] = useState<Job | null>(null);
  const [titleDraft, setTitleDraft] = useState("");
  const titleBusy = actions.busy?.action === 'title';
  const titleError = renameJob ? actions.errors[`${renameJob.id}:title`] || '' : '';
  function beginRename(job: Job) {
    setRenameJob(job); setTitleDraft(jobTitle(job)); actions.clearError(job.id, 'title');
  }
  async function saveTitle() {
    if (!renameJob) return;
    const updated = await actions.rename(renameJob, titleDraft);
    if (updated) {
      setJobs(current => current.map(job => job.id === updated.id ? { ...job, ...updated } : job));
      setRenameJob(null);
    }
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
                ...(playable(job) ? [{ id: "cover", label: "编辑封面", disabled: building(job), onSelect: () => setCoverJob(job) }] : []),
                { id: "rename", label: "重命名", disabled: building(job) || Boolean(actionBusy), onSelect: () => beginRename(job) },
                ...(playable(job) ? [
                  { id: "publish", label: !publications[job.id] ? "读取发布状态…" : publications[job.id].published ? "更新发布" : "发布", disabled: !publications[job.id] || building(job) || Boolean(actionBusy), onSelect: () => void changePublication(job) },
                  ...(publications[job.id]?.published ? [{ id: "unpublish", label: "取消生态发布", disabled: building(job) || Boolean(actionBusy), onSelect: () => void changePublication(job, true) }] : []),
                  { id: "practice", label: "打开习题", href: withBasePath(`/practice/${job.id}`) },
                  { id: "flow", label: "流程图", onSelect: () => setFlowJob(job) },
                ] : []),
                { id: "delete", label: "删除任务", destructive: true, disabled: building(job) || Boolean(actionBusy), onSelect: () => { actions.clearError(job.id, "delete"); setDeleteJob(job); } },
              ]}>
              <div className="history-cover">{playable(job) ? <ImagePreview src={withBasePath(`/play/${job.id}/cover?revision=${job.published_revision ?? 0}&cover=${job.cover_revision ?? 0}`)} alt={`${jobTitle(job)}封面`} fallback="无封面" loading="lazy" /> : <span>封面待生成</span>}</div>
              <div className="history-row-main">
                <div className="history-title-line">
                  <h2><Link className="history-card-link" href={editorHref(job)} aria-label={`打开作品：${jobTitle(job)}`}>{jobTitle(job)}</Link></h2>
                  <button className="history-title-edit" type="button" aria-label={`重命名作品：${jobTitle(job)}`} title="重命名作品" disabled={building(job) || Boolean(actionBusy)} onClick={() => beginRename(job)}>
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
              <div className="asset-confirm-actions"><Button variant="outline" type="button" busy={Boolean(titleBusy)} onClick={() => setRenameJob(null)}>取消</Button><Button variant="primary" type="submit" busy={Boolean(titleBusy)} disabled={titleBusy || !titleDraft.trim()}>保存</Button></div>
            </form>
          </section></ModalBody></div>
        </ModalFrame>}
        {coverJob && <EditCoverDialog job={coverJob} onClose={() => setCoverJob(null)} onSaved={updated => { setJobs(current => current.map(job => job.id === updated.id ? { ...job, ...updated } : job)); setCoverJob(null); }} />}
        {flowJob && <PublishedFlowModal job={flowJob} onClose={() => setFlowJob(null)} />}
      </main>
    </>
  );
}
