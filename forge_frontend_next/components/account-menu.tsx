"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { AccountMenu as SharedAccountMenu } from "@narrativeos/ui";
import { accountClient, accountSettingsUrl, teacherResourcePlazaUrl } from "../app/invite-identity";
import { withBasePath } from "../app/base-path";

// Next Link adds basePath itself; API requests and plain anchors still use withBasePath.
const routeHref = (path: string) => path;

export function AccountMenu({ className, tour, dock }: { className?: string; tour?: string; dock?: { loginContent: ReactNode; loginLabel?: string } }) {
  return <SharedAccountMenu client={accountClient} href={routeHref} LinkComponent={Link}
    loginHref={() => withBasePath("/login")} plazaHref={teacherResourcePlazaUrl} settingsHref={accountSettingsUrl()}
    onLogout={() => window.location.assign(withBasePath("/"))}
    className={className} tour={tour} dock={dock} includeAdmin />;
}
