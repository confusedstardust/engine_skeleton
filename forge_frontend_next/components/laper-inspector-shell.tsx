"use client";

import type { ReactNode } from "react";

type InspectorStat = {
  label: string;
  value: string | number;
};

type LaperInspectorShellProps = {
  eyebrow?: string;
  title: string;
  stats?: InspectorStat[];
  note?: string;
  children?: ReactNode;
  footer?: ReactNode;
};

export function LaperInspectorShell(props: LaperInspectorShellProps) {
  return (
    <div className="laper-inspector-inner">
      <div className="laper-inspector-head">
        {props.eyebrow && <span>{props.eyebrow}</span>}
        <strong>{props.title}</strong>
      </div>

      {props.stats && props.stats.length > 0 && (
        <div className="laper-stats">
          {props.stats.map((item) => (
            <div className="laper-stat-card" key={item.label}>
              <strong>{item.value}</strong>
              <span>{item.label}</span>
            </div>
          ))}
        </div>
      )}

      {props.children}

      {props.note && <p className="laper-inspector-note">{props.note}</p>}

      {props.footer && <div className="laper-inspector-actions">{props.footer}</div>}
    </div>
  );
}
