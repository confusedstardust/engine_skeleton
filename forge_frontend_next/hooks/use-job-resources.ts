'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { forgeApi } from '../lib/api-client';
import type { NodesResponse } from '../domain/jobs';
import type { AssetReviewResponse } from '../domain/assets';
import { usePolling } from './use-polling';

export function useJobResources(
  jobId: string,
  onMessage: (message: string) => void,
  onError: (message: string) => void,
) {
  const [data, setData] = useState<NodesResponse | null>(null);
  const [assetReview, setAssetReview] = useState<AssetReviewResponse | null>(null);
  const [reviewFailed, setReviewFailed] = useState(false);
  const generation = useRef(0);
  const handlers = useRef({ onMessage, onError });
  useEffect(() => {
    handlers.current = { onMessage, onError };
  });
  useEffect(
    () => () => {
      generation.current += 1;
    },
    [jobId],
  );
  const load = useCallback(
    async (signal?: AbortSignal) => {
      const current = ++generation.current;
      const [nodes, review] = await Promise.allSettled([
        forgeApi<NodesResponse>(`/jobs/${jobId}/nodes`, { signal }),
        forgeApi<AssetReviewResponse>(`/jobs/${jobId}/assets/review`, { signal }),
      ]);
      if (!signal?.aborted && current === generation.current) {
        if (nodes.status === 'fulfilled') setData(nodes.value);
        if (review.status === 'fulfilled') setAssetReview(review.value);
        setReviewFailed(review.status === 'rejected');
        if (review.status === 'rejected') handlers.current.onError(review.reason instanceof Error ? review.reason.message : '素材审阅加载失败。');
      }
      if (nodes.status === 'rejected') throw nodes.reason;
      return { next: nodes.value, reviewFailed: review.status === 'rejected' };
    },
    [jobId],
  );
  const refresh = useCallback(
    async (silent = false) => {
      try {
        const result = await load();
        if (!silent && !result.reviewFailed) handlers.current.onMessage('任务内容已更新。');
      } catch (error) {
        handlers.current.onError(error instanceof Error ? error.message : '读取任务失败。');
      }
    },
    [load],
  );
  useEffect(() => {
    const onFocus = () => { void refresh(true); };
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [refresh]);
  usePolling(
    async (signal) => {
      const { next, reviewFailed } = await load(signal);
      return reviewFailed || ['RUNNING', 'QUEUED'].includes(next.job.status) || next.job.build_state === 'BUILDING';
    },
    {
      intervalMs: 2200,
      resetKey: jobId,
      enabled: reviewFailed || !data || ['RUNNING', 'QUEUED'].includes(data.job.status) || data.job.build_state === 'BUILDING',
      onError: (error) => handlers.current.onError(error instanceof Error ? error.message : '读取任务失败。'),
    },
  );
  return { data, setData, assetReview, refresh };
}
