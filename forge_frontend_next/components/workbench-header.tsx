"use client";

import type { ReactNode } from "react";
import { WorkspaceHeader } from "@narrativeos/ui/workspace-chrome";
import { portalHref } from "@narrativeos/ui/app-links";
import { useBrowserOrigin } from "@narrativeos/ui/workspace-sidebar";
import BrandLogo from "./brand-logo";
import { useLeaveGuard } from "./workspace-leave-guard";

export function WorkbenchHeader({ title, subtitle, children }: {
  title: ReactNode; subtitle?: ReactNode; children?: ReactNode;
}) {
  const origin = useBrowserOrigin();
  const plaza = portalHref("/teacher-ecosystem/", origin, process.env.NEXT_PUBLIC_SSO_ORIGIN);
  const guard = useLeaveGuard();
  return <WorkspaceHeader title={title} subtitle={subtitle} logo={<BrandLogo size={34} rounded={false} />}
    back={{ fallback: plaza, siblingApp: plaza, ready: Boolean(origin), confirmNavigation: guard.confirm }}
    actions={children} />;
}
