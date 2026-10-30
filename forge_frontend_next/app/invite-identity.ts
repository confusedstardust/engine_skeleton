"use client";

import { createAccountClient } from "@narrativeos/ui/client";
import { withBasePath } from "./base-path";
import { forgeApi } from "../lib/api-client";

export { clearStoredInviteCode, getStoredInviteCode, setStoredInviteCode, inviteHeaders, jsonAuthHeaders, inviteHeaderName, inviteStorageKey, type AuthUser, type CreditBalance } from "@narrativeos/ui/client";

export type AuthMode = "invite" | "sso" | "sso_or_invite";

export async function getAuthMode(): Promise<AuthMode | null> {
  try {
    const payload = await forgeApi<{ mode?: unknown }>("/auth/config");
    return payload.mode === "invite" || payload.mode === "sso" || payload.mode === "sso_or_invite" ? payload.mode : null;
  } catch { return null; }
}

export function ssoLoginUrl(returnPath = "/") {
  if (typeof window === "undefined") return "/login/";
  const configuredOrigin = (process.env.NEXT_PUBLIC_SSO_ORIGIN || "").replace(/\/$/, "");
  const localWebsiteOrigin = `${window.location.protocol}//${window.location.hostname}:3000`;
  const origin = configuredOrigin || (window.location.port === "3001" ? localWebsiteOrigin : window.location.origin);
  const returnUrl = new URL(withBasePath(returnPath), window.location.origin).toString();
  return `${origin}/login/?next=${encodeURIComponent(returnUrl)}`;
}

export function accountSettingsUrl() {
  if (typeof window === "undefined") return "/account";
  return new URL("/account", ssoLoginUrl("/")).toString();
}

export function teacherResourcePlazaUrl() {
  if (typeof window === "undefined") return "/teacher-ecosystem/";
  const url = new URL("/teacher-ecosystem/", ssoLoginUrl("/"));
  url.searchParams.set("returnTo", window.location.origin + window.location.pathname + window.location.search);
  return url.toString();
}

export const accountClient = createAccountClient({
  apiUrl: path => withBasePath(`/api/forge${path}`),
  logoutUrl: () => new URL("/api/auth/logout", ssoLoginUrl("/")).href,
});
export const { getCurrentUser, getCreditBalance } = accountClient;
