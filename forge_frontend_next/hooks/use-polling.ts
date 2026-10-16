'use client';

import { useEffect, useRef } from 'react';
import { startPolling, type PollingOptions } from '../lib/polling';

export function usePolling(
  task: (signal: AbortSignal) => Promise<boolean | void>,
  options: Omit<PollingOptions, 'slot'> & { enabled?: boolean; resetKey?: string },
) {
  const taskRef = useRef(task);
  const errorRef = useRef(options.onError);
  const slot = useRef<Promise<void> | null>(null);
  useEffect(() => {
    taskRef.current = task;
    errorRef.current = options.onError;
  });
  const { enabled = true, intervalMs, maxIntervalMs, immediate, resetKey } = options;
  useEffect(() => {
    if (!enabled) return;
    return startPolling((signal) => taskRef.current(signal), {
      intervalMs,
      maxIntervalMs,
      immediate,
      slot,
      onError: (error) => errorRef.current?.(error),
    });
  }, [enabled, intervalMs, maxIntervalMs, immediate, resetKey]);
}
