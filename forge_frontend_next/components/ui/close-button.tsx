'use client';
import { forwardRef, type ComponentPropsWithoutRef } from 'react';
import styles from './close-button.module.css';

export const CloseButton = forwardRef<HTMLButtonElement, Omit<ComponentPropsWithoutRef<'button'>, 'children'> & { size?: 'sm' | 'md'; tone?: 'default' | 'inverse' }>(function CloseButton(
  { className, size = 'md', tone = 'default', type = 'button', 'aria-label': label = '关闭', ...props }, ref,
) {
  return <button {...props} ref={ref} type={type} aria-label={label} className={`${styles.close} ${size === 'sm' ? styles.small : ''} ${tone === 'inverse' ? styles.inverse : ''} ${className ?? ''}`}>
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true" focusable="false"><path d="m6 6 12 12M18 6 6 18" /></svg>
  </button>;
});
