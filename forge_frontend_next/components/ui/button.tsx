'use client';
import { forwardRef, type ComponentPropsWithoutRef } from 'react';

export type ButtonProps = ComponentPropsWithoutRef<'button'> & {
  variant?: 'primary' | 'outline' | 'ghost' | 'unstyled';
  busy?: boolean;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'outline', type = 'button', busy = false, disabled, className, children, ...props }, ref,
) {
  const pending = busy || props['aria-busy'] === true || props['aria-busy'] === 'true';
  return <button {...props} ref={ref} type={type} className={variant === 'unstyled' ? className : `btn ${variant}${className ? ` ${className}` : ''}`}
    disabled={disabled || pending} aria-busy={pending || undefined}>{children}</button>;
});
