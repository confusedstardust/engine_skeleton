"use client";

import Link from "next/link";
import { Menu, PanelLeft } from "lucide-react";
import type { ReactNode } from "react";
import BrandLogo from "../brand-logo";
import { Button } from "./button";
import styles from "./workspace-sidebar.module.css";

export type WorkspaceNavLink = {
  label: string;
  icon: ReactNode;
  href: string;
  current?: boolean;
  external?: boolean;
};

type SidebarAction = {
  label: string;
  icon: ReactNode;
  onClick: () => void;
  disabled?: boolean;
};

/** Reusable navigation surface; each workbench supplies its own routes and content. */
export function WorkspaceSidebar({
  className = "",
  expanded,
  onToggle,
  title = "NarrativeOS",
  tagline = "让知识成为探索",
  links,
  action,
  children,
  footer,
  ariaLabel = "工作台导航",
}: {
  className?: string;
  expanded: boolean;
  onToggle: () => void;
  title?: string;
  tagline?: string;
  links: WorkspaceNavLink[];
  action?: SidebarAction;
  children?: ReactNode;
  footer?: ReactNode;
  ariaLabel?: string;
}) {
  const collapsed = !expanded;
  const itemContent = (item: WorkspaceNavLink) => <>{item.icon}<span className={styles.itemLabel}>{item.label}</span></>;
  return <aside className={[styles.root, className].filter(Boolean).join(" ")}
    data-collapsed={collapsed} aria-label={ariaLabel}>
    <div className={styles.heading}>
      <Link className={styles.brand} href="/" aria-label="NarrativeOS 首页">
        <BrandLogo size={34} rounded={false} />
        <span><strong>{title}</strong><small>{tagline}</small></span>
      </Link>
      <Button variant="unstyled" className={styles.toggle} iconOnly onClick={onToggle}
        aria-label={expanded ? "收起侧栏" : "展开侧栏"}
        aria-expanded={expanded} title={expanded ? "收起侧栏" : "展开侧栏"}>
        {expanded ? <PanelLeft size={19} strokeWidth={1.65} aria-hidden="true"/> : <Menu size={19} strokeWidth={1.65} aria-hidden="true"/>}
      </Button>
    </div>
    <nav className={styles.links} aria-label={ariaLabel}>
      {links.map(item => {
        const shared = { title: item.label, "aria-label": item.label,
          "aria-current": item.current ? "page" as const : undefined,
          className: [styles.item, item.current ? styles.active : ""].filter(Boolean).join(" ") };
        return item.external
          ? <a key={item.label} {...shared} href={item.href}>{itemContent(item)}</a>
          : <Link key={item.label} {...shared} href={item.href}>{itemContent(item)}</Link>;
      })}
    </nav>
    {action && <div className={styles.primaryAction}>
      <Button variant="unstyled" className={styles.action} disabled={action.disabled}
        onClick={action.onClick} title={action.label} aria-label={action.label}>
        {action.icon}<span className={styles.itemLabel}>{action.label}</span>
      </Button>
    </div>}
    {children && <div className={styles.extra}>{children}</div>}
    {footer && <div className={styles.footer}>{footer}</div>}
  </aside>;
}
