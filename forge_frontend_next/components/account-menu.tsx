"use client";

import Link from "next/link";
import { AccountMenu as SharedAccountMenu } from "@narrativeos/ui";
import { accountClient, teacherResourcePlazaUrl } from "../app/invite-identity";
import { withBasePath } from "../app/base-path";

// Next Link adds basePath itself; API requests and plain anchors still use withBasePath.
const routeHref = (path: string) => path;

export function AccountMenu({ className, tour, includeAdmin = false }: { className?: string; tour?: string; includeAdmin?: boolean }) {
  return <SharedAccountMenu client={accountClient} href={routeHref} LinkComponent={Link}
    loginHref={() => withBasePath("/login")} plazaHref={teacherResourcePlazaUrl}
    onLogout={() => window.location.assign(withBasePath("/"))}
    className={className} tour={tour} includeAdmin={includeAdmin} />;
}
