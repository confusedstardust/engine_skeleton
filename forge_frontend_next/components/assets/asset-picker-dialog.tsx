'use client';
import { LoadingState } from '../ui/state';
import { InlineFeedback } from '../ui/feedback';

import { Button } from '../ui/button';
import { useEffect, useRef, useState } from 'react';
import type { PersonalLibraryAsset } from '../../domain/assets';
import { useIncrementalList } from '../../hooks/use-incremental-list';
import { AssetPreview } from './asset-preview';
import { AssetCard } from './asset-card';
import { ContentDialog } from '../ui/content-dialog';

export function AssetPickerDialog<T extends Pick<PersonalLibraryAsset, 'file_id' | 'name' | 'mime_type' | 'url'>>({
  title,
  load,
  onSelect,
  onClose,
}: {
  title: string;
  load: (page: number, signal: AbortSignal) => Promise<{ assets: T[]; has_more: boolean }>;
  onSelect: (asset: T) => Promise<boolean>;
  onClose: () => void;
}) {
  const list = useIncrementalList({
    resetKey: title,
    initialCursor: 1,
    keyOf: (asset: T) => asset.file_id,
    load: async (page, signal) => {
      const data = await load(page, signal);
      return { items: data.assets, next: page + 1, hasMore: data.has_more };
    },
  });
  const [selected, setSelected] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  function more(element: HTMLDivElement) {
    if (
      !list.loading &&
      !list.error &&
      list.hasMore &&
      element.scrollHeight - element.scrollTop - element.clientHeight <= 80
    )
      void list.loadNext();
  }
  async function apply() {
    const asset = list.items.find((item) => item.file_id === selected);
    if (!asset || busy) return;
    setBusy(true);
    setError('');
    try {
      const ok = await onSelect(asset);
      if (mounted.current) {
        if (ok) onClose();
        else setError('素材调用失败，请重试');
      }
    } catch (reason) {
      if (mounted.current) setError(reason instanceof Error ? reason.message : '素材调用失败，请重试');
    } finally {
      if (mounted.current) setBusy(false);
    }
  }
  return (
    <ContentDialog title={title} busy={busy} onClose={onClose} closeInHeader={false} layerClassName="asset-library-picker-layer" className="asset-library-picker" bodyClassName="asset-library-picker-body"
      bodyProps={{ onScroll: event => more(event.currentTarget), onWheel: event => { if (event.deltaY > 0) more(event.currentTarget); } }}
      footer={<footer className="asset-modal-actions">
              <Button variant="outline" busy={Boolean(busy)} onClick={onClose}>
                取消
              </Button>
              <Button variant="primary" busy={Boolean(busy)} disabled={!selected || busy} onClick={() => void apply()}>
                {busy ? '正在使用…' : '使用此素材'}
              </Button>
            </footer>}>
              {list.loading && !list.items.length ? (
                <LoadingState className="asset-library-picker-state">
                  正在加载素材…
                </LoadingState>
              ) : null}
              {list.error ? (
                <InlineFeedback as="div" className="asset-library-picker-state" >
                  {list.error}
                  <Button variant="outline" onClick={() => void list.loadNext()}>
                    重试
                  </Button>
                </InlineFeedback>
              ) : null}
              {!list.loading && !list.error && !list.items.length ? (
                <div className="asset-library-picker-state">暂无可选素材</div>
              ) : null}
              <div className="asset-library-picker-grid" role="listbox" aria-label="可选素材">
                {list.items.map((asset) => (
                  <AssetCard variant="picker" key={asset.file_id} name={asset.name}
                    selected={selected === asset.file_id} disabled={busy} onSelect={() => setSelected(asset.file_id)}
                    preview={<AssetPreview asset={asset} interactive={false} decorative audioClassName="asset-library-audio-mark" />} />
                ))}
              </div>
              {list.loading && list.items.length ? (
                <LoadingState inline className="asset-library-picker-more">
                  正在加载更多素材…
                </LoadingState>
              ) : null}
              {!list.loading && !list.error && list.hasMore ? (
                <Button variant="outline" onClick={() => void list.loadNext()}>
                  加载更多
                </Button>
              ) : null}
              {error ? <InlineFeedback >{error}</InlineFeedback> : null}
    </ContentDialog>
  );
}
