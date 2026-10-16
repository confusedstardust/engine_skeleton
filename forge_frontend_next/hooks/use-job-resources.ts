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
      const [next, review] = await Promise.all([
        forgeApi<NodesResponse>(`/jobs/${jobId}/nodes`, { signal }),
        forgeApi<AssetReviewResponse>(`/jobs/${jobId}/assets/review`, { signal }),
      ]);
      if (!signal?.aborted && current === generation.current) {
        setData(next);
        setAssetReview(review);
      }
      return next;
    },
    [jobId],
  );
  const refresh = useCallback(
    async (silent = false) => {
      try {
        await load();
        if (!silent) handlers.current.onMessage('任务内容已更新。');
      } catch (error) {
        handlers.current.onError(error instanceof Error ? error.message : '读取任务失败。');
      }
    },
    [load],
  );
  usePolling(
    async (signal) => {
      const next = await load(signal);
      return ['RUNNING', 'QUEUED'].includes(next.job.status) || next.job.build_state === 'BUILDING';
    },
    {
      intervalMs: 2200,
      resetKey: jobId,
      enabled: !data || ['RUNNING', 'QUEUED'].includes(data.job.status) || data.job.build_state === 'BUILDING',
      onError: (error) => handlers.current.onError(error instanceof Error ? error.message : '读取任务失败。'),
    },
  );
  return { data, setData, assetReview, refresh };
}
