import type { ComponentPropsWithoutRef } from 'react';
import styles from './dialog-actions.module.css';

export function DialogActions({ as: Tag = 'div', className, ...props }: ComponentPropsWithoutRef<'div'> & { as?: 'div' | 'footer' }) {
  return <Tag {...props} className={`${styles.actions} ${className ?? ''}`} />;
}
