'use client';
import type { ComponentPropsWithoutRef, ReactNode } from 'react';
import styles from './state.module.css';

type StateProps = ComponentPropsWithoutRef<'div'> & { as?: 'div' | 'section' | 'p' | 'span'; title?: string; description?: ReactNode; action?: ReactNode };
export function EmptyState({ as: Tag = 'div', className, title, description, action, children, ...props }: StateProps) {
  return <Tag {...props} className={`${styles.state} ${className ?? ''}`}>
    {title && <strong>{title}</strong>}{description && <p>{description}</p>}{children}{action && <div className={styles.actions}>{action}</div>}
  </Tag>;
}
export function Spinner({ as: Tag = 'span', size = 'md', tone = 'accent', className, ...props }: ComponentPropsWithoutRef<'span'> & { as?: 'span' | 'div'; size?: 'sm' | 'md' | 'lg'; tone?: 'accent' | 'current' | 'gold' }) {
  return <Tag {...props} className={`${styles.spinner} pending-spinner ${className ?? ''}`} data-size={size} data-tone={tone} aria-hidden="true" />;
}
export function LoadingState({ as: Tag = 'div', children = '正在加载…', withSpinner = true, inline = false, className, ...props }: StateProps & { withSpinner?: boolean; inline?: boolean }) {
  return <Tag {...props} className={`${styles.state} ${withSpinner ? styles.loading : ''} ${inline ? styles.inline : ''} ${className ?? ''}`} role="status" aria-live="polite" aria-atomic="true">{withSpinner && <Spinner size={inline ? 'sm' : 'md'} />}{children}</Tag>;
}
