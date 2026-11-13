import type { ReactNode } from 'react';

export function ChartCard({ title, caption, children, className = 'admin-chart-card' }: {
  title: string; caption?: ReactNode; children: ReactNode; className?: string;
}) {
  return <article className={className}><h3>{title}</h3>{children}{caption && <p>{caption}</p>}</article>;
}
