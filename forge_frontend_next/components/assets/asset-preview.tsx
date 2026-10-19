'use client';

import { AudioPreview } from './audio-preview';

export type PreviewAsset = { url: string; name: string; mime_type: string; kind?: string; duration_ms?: number | null };
export function AssetPreview({
  asset,
  interactive = true,
  decorative = false,
  fallback = '素材',
  audioClassName,
}: {
  asset: PreviewAsset;
  interactive?: boolean;
  decorative?: boolean;
  fallback?: string;
  audioClassName?: string;
}) {
  if (asset.mime_type.startsWith('image/'))
    return <img src={asset.url} alt={decorative ? '' : asset.name} loading="lazy" decoding="async" />;
  if (asset.mime_type.startsWith('audio/'))
    return interactive ? (
      <AudioPreview src={asset.url} name={asset.name} durationMs={asset.duration_ms} />
    ) : (
      <span className={audioClassName} aria-hidden={decorative || undefined}>
        {decorative ? '♫' : '音频'}
      </span>
    );
  return <span>{fallback}</span>;
}
