'use client';
import { useState, type ImgHTMLAttributes } from 'react';

type Props = Omit<ImgHTMLAttributes<HTMLImageElement>, 'src'> & {
  src?: string | null;
  fallback?: string;
};

export function ImagePreview(props: Props) {
  return <ImageResource key={props.src || ''} {...props} />;
}

function ImageResource({ src, alt = '', fallback = '图片暂不可用', className, onError, onLoad, ...props }: Props) {
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  if (!src || failed) return <span className={`image-preview-empty ${className || ''}`} role="img" aria-label={fallback}>{fallback}</span>;
  return <img {...props} src={src} alt={alt} className={className} data-loading={!loaded || undefined}
    onLoad={event => { setLoaded(true); onLoad?.(event); }}
    onError={event => { setFailed(true); onError?.(event); }} />;
}
