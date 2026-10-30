'use client';
import type { ComponentPropsWithoutRef, ReactNode } from 'react';
import styles from './feedback.module.css';

type FeedbackProps = ComponentPropsWithoutRef<'div'> & {
  as?: 'div' | 'p' | 'small' | 'section' | 'span';
  tone?: 'error' | 'info' | 'success';
  action?: ReactNode;
  variant?: 'panel' | 'inline';
};
export function InlineFeedback({ as: Tag = 'p', tone = 'error', variant = 'panel', className, children, action, role, ...props }: FeedbackProps) {
  return <Tag {...props} className={`${styles.feedback} ${className ?? ''}`} data-tone={tone} data-variant={variant}
    role={role ?? (tone === 'error' ? 'alert' : 'status')} aria-atomic="true">
    {children}{action && <span className={styles.action}>{action}</span>}
  </Tag>;
}
