'use client';
import { forwardRef, type ComponentPropsWithoutRef } from 'react';
import styles from './table.module.css';

type DataTableProps = ComponentPropsWithoutRef<'table'> & { density?: 'comfortable' | 'compact'; stickyHeader?: boolean };
export const DataTable = forwardRef<HTMLTableElement, DataTableProps>(function DataTable({ className, density = 'comfortable', stickyHeader = false, ...props }, ref) {
  return <table {...props} ref={ref} data-density={density} data-sticky-header={stickyHeader || undefined} className={`${styles.table} ${className ?? ''}`} />;
});
