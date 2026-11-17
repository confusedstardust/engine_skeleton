"use client";

import "@fontsource/noto-sans-sc/400.css";
import "@fontsource/noto-sans-sc/500.css";
import "@fontsource/noto-sans-sc/600.css";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOpen, FolderOpen } from "lucide-react";
import type { MouseEvent, ReactNode } from "react";
import { WorkspaceFrame } from "@narrativeos/ui/workspace-chrome";
import { WorkspaceSidebar, useBrowserOrigin, useWorkspaceSidebar } from "@narrativeos/ui/workspace-sidebar";
import { portalHref } from "@narrativeos/ui/app-links";
import { agentRoute } from "../lib/workspace-routes";
import { AccountMenu } from "./account-menu";
import BrandLogo from "./brand-logo";
import SiteFooter from "./site-footer";
import { WorkbenchHeader } from "./workbench-header";
import { useLeaveGuard, WorkspaceLeaveGuard } from "./workspace-leave-guard";

function ForgeWorkspace({ path, children }: { path: string; children: ReactNode }) {
  const { desktop, expanded, setOpen } = useWorkspaceSidebar();
  const origin = useBrowserOrigin();
  const plaza = portalHref("/teacher-ecosystem/", origin, process.env.NEXT_PUBLIC_SSO_ORIGIN);
  const guard = useLeaveGuard();

  async function guardLink(event: MouseEvent<HTMLDivElement>) {
    if (!guard.hasConfirmation() || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target instanceof Element
      ? event.target.closest<HTMLAnchorElement>("[data-workspace-sidebar] a[href], [data-workspace-header] a[href], [data-workspace-footer] a[href]")
      : null;
    if (!link || link.target === "_blank" || link.hasAttribute("download") || link.getAttribute("href")?.startsWith("#")) return;
    event.preventDefault();
    if (await guard.confirm()) location.assign(link.href);
  }

  function navigate(event: MouseEvent<HTMLAnchorElement>) {
    if (!event.defaultPrevented && !desktop) setOpen(false);
  }

  const header = path === "/payment-test" ? "支付测试"
    : path.startsWith("/jobs/") ? "生成工作台"
    : path.startsWith("/practice/works/") ? "互动学习作品"
    : path.startsWith("/practice/s/") ? "班级习题"
    : path.startsWith("/practice/chat/") ? "互动学习创作" : undefined;

  return <div onClickCapture={guardLink}><WorkspaceFrame
    sidebar={<WorkspaceSidebar ariaLabel="工作台导航" expanded={expanded} onToggle={() => setOpen(!expanded)}
      toggleLabel={expanded ? "收起侧栏" : "展开侧栏"} brandHref="/" tagline="创造新的知识互动体验"
      LinkComponent={Link} logo={size => <BrandLogo size={size} rounded={false} />}
      links={{
        discover: { href: plaza, external: true, onClick: navigate },
        create: { href: "/practice", current: path === "/" || path.startsWith("/jobs/"), onClick: navigate },
        works: { href: "/history", current: path === "/history" || path.startsWith("/practice/works/"), onClick: navigate },
        assets: { href: "/assets", current: path === "/assets", onClick: navigate },
      }}
      secondaryLinks={[
        { label: "讲练工具", href: "/practice/resources", current: path === "/practice/resources", icon: <BookOpen aria-hidden="true" />, onClick: navigate },
        { label: "我的素材", href: "/my-assets", current: path === "/my-assets", icon: <FolderOpen aria-hidden="true" />, onClick: navigate },
      ]}
      footer={<AccountMenu dock tour={path === "/" ? "invite" : undefined} />}
    />}
    header={header && <WorkbenchHeader title={header} />}
    footer={<SiteFooter />}
  >{children}</WorkspaceFrame></div>;
}

export default function ForgeChrome({ children }: { children: ReactNode }) {
  const path = usePathname().replace(/\/+$/, "") || "/";
  if (path === "/play" || path.startsWith("/play/") || path === "/support/embed") return children;
  return <WorkspaceLeaveGuard>{agentRoute(path) ? children : <ForgeWorkspace path={path}>{children}</ForgeWorkspace>}</WorkspaceLeaveGuard>;
}
