import type { ReactNode } from 'react';

export function AnalyticsPanel({ title, extra, className = '', children }: { title: string; extra?: ReactNode; className?: string; children: ReactNode }) {
  return <section className={`cq-panel ${className}`}><header className="cq-panel-heading"><h3>{title}</h3>{extra}</header>{children}</section>;
}

export function WorkspaceHeading({ title, meta, children }: { title: string; meta?: ReactNode; children?: ReactNode }) {
  return <header className="cq-workspace-heading"><div><h2>{title}</h2>{meta && <span className="cq-workspace-count">{meta}</span>}</div>{children}</header>;
}
