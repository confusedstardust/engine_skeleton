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

export async function getCurrentUser(): Promise<AuthUser | null> {
  try {
    const response = await fetch(withBasePath("/api/forge/auth/me"), {
      credentials: "include",
      cache: "no-store",
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
  return headers;
}
