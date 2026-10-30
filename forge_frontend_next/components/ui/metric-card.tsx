import type { ReactNode } from 'react';

type MetricCardProps = {
  label: string;
  value: ReactNode;
  unit?: string;
  caption?: string;
  variant?: 'classroom' | 'admin' | 'compact';
};

// Variants retain each workspace's visual style while sharing the metric structure.
export function MetricCard({ label, value, unit, caption, variant = 'classroom' }: MetricCardProps) {
  const compact = variant === 'compact';
  const Label = variant === 'admin' ? 'h3' : 'span';
  const Caption = variant === 'admin' ? 'p' : 'footer';
  const labelNode = <Label>{label}</Label>;
  return <article className={{ classroom: 'cq-kpi', admin: 'admin-metric', compact: 'laper-stat-card' }[variant]}>
    {!compact && labelNode}
    <strong>{value}{unit && <small>{unit}</small>}</strong>
    {compact && labelNode}
    {caption && <Caption>{caption}</Caption>}
  </article>;
}
