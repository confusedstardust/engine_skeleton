'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { forgeApi as api } from '../lib/api-client';
import type { Job } from '../domain/jobs';

export type Publication = { published: boolean; work?: { title: string; playUrl: string } };
type Action = 'publication' | 'title' | 'delete';
export function workIsBuilding(job: Job) {
  return job.status === 'RUNNING' || job.status === 'QUEUED' || job.build_state === 'BUILDING';
}
export function workIsPlayable(job: Job) {
  return job.has_published_build ?? job.status === 'DONE';
}
export function workTitle(job: Job) {
  return job.title?.trim() || String(job.options?.classroom_topic || '').trim() ||
    job.source_material?.split(/\r?\n/).find(line => line.trim())?.trim().replace(/^课堂主题[:：]\s*/, '').slice(0, 36) || '未命名游戏';
}

export function useWorkActions({ confirm, notify }: {
  confirm: (message: string) => Promise<boolean>;
  notify: (message: string, kind: 'success' | 'error') => void;
}) {
  const [publications, setPublications] = useState<Record<string, Publication>>({});
  const [busy, setBusy] = useState<{ jobId: string; action: Action } | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const lock = useRef<string | null>(null);
  const reads = useRef(new Set<string>());
  const versions = useRef<Record<string, number>>({});
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const clearError = useCallback((jobId: string, action: Action) => {
    setErrors(current => ({ ...current, [`${jobId}:${action}`]: '' }));
  }, []);
  const loadPublication = useCallback(async (job: Job) => {
    if (!workIsPlayable(job) || reads.current.has(job.id) || lock.current === job.id) return;
    reads.current.add(job.id);
    const version = versions.current[job.id] = (versions.current[job.id] || 0) + 1;
    try {
      const value = await api<Publication>(`/jobs/${job.id}/ecosystem-publication`);
      if (mounted.current && versions.current[job.id] === version) {
        setPublications(current => ({ ...current, [job.id]: value }));
        clearError(job.id, 'publication');
      }
    } catch (error) {
      if (mounted.current && versions.current[job.id] === version) {
        const message = error instanceof Error ? error.message : '发布状态读取失败，请重试。';
        setErrors(current => ({ ...current, [`${job.id}:publication`]: message }));
        notify(message, 'error');
      }
    } finally { reads.current.delete(job.id); }
  }, [clearError, notify]);
  async function execute<T>(job: Job, action: Action, task: () => Promise<T | null>, fallback: string, success?: string) {
    if (lock.current || workIsBuilding(job)) return null;
    lock.current = job.id;
    if (action !== 'title') versions.current[job.id] = (versions.current[job.id] || 0) + 1;
    setBusy({ jobId: job.id, action });
    clearError(job.id, action);
    try {
      const result = await task();
      if (!mounted.current) return null;
      if (result !== null && success) notify(success, 'success');
      return result;
    } catch (error) {
      if (mounted.current) {
        const message = error instanceof Error ? error.message : fallback;
        setErrors(current => ({ ...current, [`${job.id}:${action}`]: message }));
        if (action === 'publication') notify(message, 'error');
      }
      return null;
    } finally {
      lock.current = null;
      if (mounted.current) setBusy(null);
    }
  }
  async function changePublication(job: Job, remove = false) {
    if (!workIsPlayable(job)) return null;
    return execute(job, 'publication', async () => {
      if (remove && !(await confirm('确定从教师资源广场中取消发布吗？游戏本身不会被删除。'))) return null;
      if (!mounted.current) return null;
      const value = await api<Publication>(`/jobs/${job.id}/ecosystem-publication`, {
        method: remove ? 'DELETE' : 'POST', ...(remove ? {} : { body: JSON.stringify({}) }),
      });
      if (mounted.current) setPublications(current => ({ ...current, [job.id]: value }));
      return value;
    }, remove ? '取消发布失败，请重试。' : '发布失败，请重试。', remove ? '已取消生态发布。' : '已发布到教师资源广场。');
  }
  async function rename(job: Job, draft: string) {
    return execute(job, 'title', async () => {
      const title = draft.trim();
      if (!title || title.length > 160) throw new Error('作品名称需为 1–160 个字符。');
      const value = await api<{ job: Job }>(`/jobs/${job.id}/title`, { method: 'PUT', body: JSON.stringify({ title }) });
      return value.job;
    }, '作品重命名失败，请重试。');
  }
  async function remove(job: Job) {
    return execute(job, 'delete', async () => {
      await api(`/jobs/${job.id}`, { method: 'DELETE' });
      return true;
    }, '删除失败，请重试。', '任务已删除。');
  }
  return { publications, busy, errors, clearError, loadPublication, changePublication, rename, remove };
}
