'use client';
import type { ReactNode } from 'react';

export type PaginationProps = {
  page: number;
  hasMore: boolean;
  onPageChange: (page: number) => void;
  disabled?: boolean;
  className?: string;
  buttonClassName?: string;
  ariaLabel?: string;
  total?: number;
  layout?: 'inline' | 'trailing-actions' | 'summary-first';
  summary?: ReactNode;
  children?: ReactNode;
  trailing?: ReactNode;
};

export function Pagination({
  page,
  hasMore,
  onPageChange,
  disabled = false,
  className,
  buttonClassName,
  ariaLabel = '列表分页',
  total,
  layout = 'inline',
  summary: customSummary,
  children,
  trailing,
}: PaginationProps) {
  const previous = (
    <button
      className={buttonClassName}
      type="button"
      disabled={disabled || page <= 1}
      onClick={() => onPageChange(Math.max(1, page - 1))}
    >
      上一页
    </button>
  );
  const next = (
    <button
      className={buttonClassName}
      type="button"
      disabled={disabled || !hasMore}
      onClick={() => onPageChange(page + 1)}
    >
      下一页
    </button>
  );
  const summary = (
    <span aria-live="polite">
      {customSummary ?? (
        <>
          第 {page} 页{total !== undefined ? ` · 共 ${total} 项` : ''}
        </>
      )}
    </span>
  );
  return (
    <nav className={className} aria-label={ariaLabel}>
      {layout === 'trailing-actions' ? (
        <>
          {summary}
          <div>
            {previous}
            {children}
            {next}
          </div>
          {trailing}
        </>
      ) : layout === 'summary-first' ? (
        <>
          {summary}
          {previous}
          {children}
          {next}
          {trailing}
        </>
      ) : (
        <>
          {previous}
          {summary}
          {children}
          {next}
          {trailing}
        </>
      )}
    </nav>
  );
}
