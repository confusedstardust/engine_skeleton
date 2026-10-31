'use client';
import { forwardRef, type ComponentPropsWithoutRef } from 'react';
import { Spinner } from './state';

export type ButtonProps = ComponentPropsWithoutRef<'button'> & {
  variant?: 'primary' | 'outline' | 'ghost' | 'unstyled';
  busy?: boolean;
  size?: 'sm' | 'md';
  iconOnly?: boolean;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'outline', type = 'button', busy = false, size = 'md', iconOnly = false, disabled, className, children, ...props }, ref,
) {
  const pending = busy || props['aria-busy'] === true || props['aria-busy'] === 'true';
  return <button {...props} ref={ref} type={type} data-size={size} data-icon-only={iconOnly || undefined} className={variant === 'unstyled' ? className : `btn ${variant}${className ? ` ${className}` : ''}`}
    disabled={disabled || pending} aria-busy={pending || undefined}>{pending && variant !== 'unstyled' && !iconOnly ? <><Spinner size="sm" tone="current" />{children}</> : children}</button>;
});
