'use client';
import type { ReactNode } from 'react';
import { CloseButton } from './close-button';
import { Title } from './dialog';
import styles from './dialog-header.module.css';

export function DialogHeader({ title, subtitle, eyebrow, onClose, busy, className, titleId, closeLabel = '关闭', dialogTitle = false }: {
  title: ReactNode; subtitle?: ReactNode; eyebrow?: ReactNode; onClose?: () => void; busy?: boolean;
  className?: string; titleId?: string; closeLabel?: string; dialogTitle?: boolean;
}) {
  const heading = <h2 {...(titleId ? { id: titleId } : {})}>{title}</h2>;
  return <header className={`${styles.header} ${className ?? ''}`}>
    <div className={styles.copy}>{eyebrow && <span>{eyebrow}</span>}{dialogTitle ? <Title asChild>{heading}</Title> : heading}{subtitle && <div className={styles.subtitle}>{subtitle}</div>}</div>
    {onClose && <CloseButton aria-label={closeLabel} disabled={busy} onClick={onClose} />}
  </header>;
}
