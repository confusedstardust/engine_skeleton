"use client";

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

export function inviteHeaders() {
  const code = getStoredInviteCode();
  return code ? { [inviteHeaderName]: encodeURIComponent(code) } : {};
}

export function jsonInviteHeaders(base?: HeadersInit) {
  const headers = new Headers(base);
  headers.set("Content-Type", "application/json");
  const code = getStoredInviteCode();
  if (code) headers.set(inviteHeaderName, encodeURIComponent(code));
  return headers;
}
