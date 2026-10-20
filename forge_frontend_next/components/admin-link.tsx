"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { AdminLink as SharedAdminLink } from "@narrativeos/ui";
import { accountMessages } from "@narrativeos/ui/i18n";
import { accountClient } from "../app/invite-identity";

export function AdminLink({ children, onClick }: { children?: ReactNode; onClick?: () => void } = {}) {
  return <SharedAdminLink client={accountClient} href="/admin" LinkComponent={Link} onClick={onClick}>{children ?? accountMessages["zh-CN"].admin}</SharedAdminLink>;
}
