'use client';
import { useEffect, useRef, useState } from 'react';
import type { PersonalLibraryAsset } from '../../domain/assets';
import { useIncrementalList } from '../../hooks/use-incremental-list';
import { AssetPreview } from './asset-preview';
import { ModalBody, ModalFrame } from '../ui/modal';

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
    <ModalFrame title={title} busy={busy} onClose={onClose}>
      <div className="asset-library-picker-layer" role="presentation">
        <button
          className="asset-modal-backdrop"
          type="button"
          aria-label="关闭素材库"
          disabled={busy}
          onClick={onClose}
        />
        <ModalBody>
          <section className="asset-library-picker" role="dialog" aria-modal="true">
            <header className="asset-modal-head">
              <h2>{title}</h2>
              <button type="button" aria-label="关闭" disabled={busy} onClick={onClose}>
                ×
              </button>
            </header>
            <div
              className="asset-library-picker-body"
              onScroll={(event) => more(event.currentTarget)}
              onWheel={(event) => {
                if (event.deltaY > 0) more(event.currentTarget);
              }}
            >
              {list.loading && !list.items.length ? (
                <div className="asset-library-picker-state" role="status">
                  正在加载素材…
                </div>
              ) : null}
              {list.error ? (
                <div className="asset-library-picker-state error" role="alert">
                  {list.error}
                  <button className="btn outline" onClick={() => void list.loadNext()}>
                    重试
                  </button>
                </div>
              ) : null}
              {!list.loading && !list.error && !list.items.length ? (
                <div className="asset-library-picker-state">暂无可选素材</div>
              ) : null}
              <div className="asset-library-picker-grid" role="listbox" aria-label="可选素材">
                {list.items.map((asset) => (
                  <button
                    className={`asset-library-picker-card ${selected === asset.file_id ? 'selected' : ''}`}
                    type="button"
                    role="option"
                    aria-selected={selected === asset.file_id}
                    disabled={busy}
                    key={asset.file_id}
                    onClick={() => setSelected(asset.file_id)}
                  >
                    <div className="asset-library-picker-preview">
                      <AssetPreview asset={asset} interactive={false} decorative audioClassName="asset-library-audio-mark" />
                    </div>
                    <div className="asset-library-picker-copy">
                      <strong>{asset.name}</strong>
                    </div>
                    <i aria-hidden="true">✓</i>
                  </button>
                ))}
              </div>
              {list.loading && list.items.length ? (
                <div className="asset-library-picker-more" role="status">
                  正在加载更多素材…
                </div>
              ) : null}
              {!list.loading && !list.error && list.hasMore ? (
                <button className="btn outline" onClick={() => void list.loadNext()}>
                  加载更多
                </button>
              ) : null}
              {error ? <p role="alert">{error}</p> : null}
            </div>
            <footer className="asset-modal-actions">
              <button className="btn outline" disabled={busy} onClick={onClose}>
                取消
              </button>
              <button className="btn primary" disabled={!selected || busy} onClick={() => void apply()}>
                {busy ? '正在使用…' : '使用此素材'}
              </button>
            </footer>
          </section>
        </ModalBody>
      </div>
    </ModalFrame>
  );
}
