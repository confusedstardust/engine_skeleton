export type PollingOptions = {
  intervalMs: number;
  maxIntervalMs?: number;
  immediate?: boolean;
  onError?: (error: unknown) => void;
  slot?: { current: Promise<void> | null };
};

/** One request at a time; false stops polling, failures retry with bounded backoff. */
export function startPolling(task: (signal: AbortSignal) => Promise<boolean | void>, options: PollingOptions) {
  const controller = new AbortController();
  const slot = options.slot ?? { current: null };
  let timer: ReturnType<typeof setTimeout> | undefined;
  let failures = 0;
  const schedule = (delay: number) => {
    if (!controller.signal.aborted) timer = setTimeout(() => void run(), delay);
  };
  async function run() {
    if (slot.current) await slot.current;
    if (controller.signal.aborted) return;
    let continuePolling = true;
    const pending = (async () => {
      try {
        continuePolling = (await task(controller.signal)) !== false;
        failures = 0;
      } catch (error) {
        if (!controller.signal.aborted) {
          failures += 1;
          options.onError?.(error);
        }
      }
    })();
    slot.current = pending;
    await pending;
    if (slot.current === pending) slot.current = null;
    if (continuePolling)
      schedule(Math.min(options.intervalMs * 2 ** Math.min(failures, 6), options.maxIntervalMs ?? 30000));
  }
  if (options.immediate !== false) void run();
  else schedule(options.intervalMs);
  return () => {
    controller.abort();
    clearTimeout(timer);
  };
}
