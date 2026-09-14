"use client";

import { withBasePath } from "./base-path";

export type AuthUser = {
  id: string;
  email: string | null;
  nickname: string | null;
  avatar_url: string | null;
  providers: string[];
  auth_type: "sso" | "invite";
};

export type AuthMode = "invite" | "sso" | "sso_or_invite";

export const inviteStorageKey = "webgal_invite_code";
export const inviteHeaderName = "X-WebGAL-Invite-Code";

export function getStoredInviteCode() {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(inviteStorageKey)?.trim() || "";
}

export function setStoredInviteCode(code: string) {
  window.localStorage.setItem(inviteStorageKey, code.trim());
}

export function clearStoredInviteCode() {
  window.localStorage.removeItem(inviteStorageKey);
}

export function inviteHeaders(): Record<string, string> {
  const code = getStoredInviteCode();
  return code ? { [inviteHeaderName]: encodeURIComponent(code) } : {};
}

export async function getAuthMode(): Promise<AuthMode | null> {
  try {
    const response = await fetch(withBasePath("/api/forge/auth/config"), { cache: "no-store" });
    if (!response.ok) return null;
    const payload = (await response.json()) as { mode?: unknown };
    return payload.mode === "invite" || payload.mode === "sso" || payload.mode === "sso_or_invite"
      ? payload.mode
      : null;
  } catch {
    return null;
  }
}

export async function getCurrentUser(): Promise<AuthUser | null> {
  try {
    const response = await fetch(withBasePath("/api/forge/auth/me"), {
      credentials: "include",
      cache: "no-store",
      headers: inviteHeaders(),
    });
    if (!response.ok) return null;
    return (await response.json()) as AuthUser;
  } catch {
    return null;
  }
}

export function ssoLoginUrl(returnPath = "/") {
  if (typeof window === "undefined") return "/login/";
  const configuredOrigin = (process.env.NEXT_PUBLIC_SSO_ORIGIN || "").replace(/\/$/, "");
  const localWebsiteOrigin = `${window.location.protocol}//${window.location.hostname}:3000`;
  const origin = configuredOrigin || (window.location.port === "3001" ? localWebsiteOrigin : window.location.origin);
  const returnUrl = new URL(withBasePath(returnPath), window.location.origin).toString();
  return `${origin}/login/?next=${encodeURIComponent(returnUrl)}`;
}

export function jsonAuthHeaders(base?: HeadersInit) {
  const headers = new Headers(base);
  headers.set("Content-Type", "application/json");
  const code = getStoredInviteCode();
  if (code) headers.set(inviteHeaderName, encodeURIComponent(code));
  return headers;
}
