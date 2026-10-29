'use client';
import type { ReactNode } from 'react';
import { CloseButton } from './close-button';
import styles from './dialog-header.module.css';

export function DialogHeader({ title, subtitle, eyebrow, onClose, busy, className, titleId, closeLabel = '关闭' }: {
  title: ReactNode; subtitle?: ReactNode; eyebrow?: ReactNode; onClose?: () => void; busy?: boolean;
  className?: string; titleId?: string; closeLabel?: string;
}) {
  return <header className={`${styles.header} ${className ?? ''}`}>
    <div className={styles.copy}>{eyebrow && <span>{eyebrow}</span>}<h2 id={titleId}>{title}</h2>{subtitle && <div className={styles.subtitle}>{subtitle}</div>}</div>
    {onClose && <CloseButton aria-label={closeLabel} disabled={busy} onClick={onClose} />}
  </header>;
}
