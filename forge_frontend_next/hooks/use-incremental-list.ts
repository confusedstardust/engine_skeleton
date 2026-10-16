'use client';
import { useEffect, useRef, useState } from 'react';
export type ListBatch<T, Cursor> = { items: T[]; next: Cursor; hasMore: boolean; total?: number };

export function useIncrementalList<T, Cursor>({
  resetKey,
  initialCursor,
  enabled = true,
  load,
  keyOf,
}: {
  resetKey: unknown;
  initialCursor: Cursor;
  enabled?: boolean;
  load: (cursor: Cursor, signal: AbortSignal) => Promise<ListBatch<T, Cursor>>;
  keyOf: (item: T) => string;
}) {
  const [items, setItems] = useState<T[]>([]);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState('');
  const [hasMore, setHasMore] = useState(false);
  const [total, setTotal] = useState(0);
  const options = useRef({ load, keyOf });
  options.current = { load, keyOf };
  const nextRef = useRef<() => Promise<void>>(async () => {});
  useEffect(() => {
    let active = true,
      pending = false,
      more = true;
    let cursor = initialCursor;
    const controller = new AbortController();
    // Capture the loader for this filter generation; never mix old and new filters.
    const loader = options.current.load;
    setItems([]);
    setTotal(0);
    setError('');
    setHasMore(false);
    setLoading(enabled);
    async function next() {
      if (!active || !enabled || pending || !more) return;
      pending = true;
      setLoading(true);
      setError('');
      try {
        const batch = await loader(cursor, controller.signal);
        if (!active) return;
        cursor = batch.next;
        more = batch.hasMore && batch.items.length > 0;
        setItems((previous) => {
          const keys = new Set(previous.map(options.current.keyOf));
          return [
            ...previous,
            ...batch.items.filter((item) => {
              const key = options.current.keyOf(item);
              if (keys.has(key)) return false;
              keys.add(key);
              return true;
            }),
          ];
        });
        setHasMore(more);
        if (batch.total !== undefined) setTotal(batch.total);
      } catch (reason) {
        if (active) setError(reason instanceof Error ? reason.message : '素材加载失败');
      } finally {
        pending = false;
        if (active) setLoading(false);
      }
    }
    nextRef.current = next;
    void next();
    return () => {
      active = false;
      controller.abort();
    };
    // initialCursor belongs to resetKey, not to every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetKey, enabled]);
  return { items, setItems, loading, error, hasMore, total, loadNext: () => nextRef.current() };
}
