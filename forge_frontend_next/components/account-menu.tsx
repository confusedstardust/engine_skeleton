"use client";

import Link from "next/link";
import { AccountMenu as SharedAccountMenu } from "@narrativeos/ui";
import { accountClient, accountSettingsUrl, teacherResourcePlazaUrl } from "../app/invite-identity";
import { withBasePath } from "../app/base-path";

// Next Link adds basePath itself; API requests and plain anchors still use withBasePath.
const routeHref = (path: string) => path;

export function AccountMenu({ className, tour }: { className?: string; tour?: string }) {
  return <SharedAccountMenu client={accountClient} href={routeHref} LinkComponent={Link}
    loginHref={() => withBasePath("/login")} plazaHref={teacherResourcePlazaUrl} settingsHref={accountSettingsUrl()}
    onLogout={() => window.location.assign(withBasePath("/"))}
    className={className} tour={tour} includeAdmin />;
}
