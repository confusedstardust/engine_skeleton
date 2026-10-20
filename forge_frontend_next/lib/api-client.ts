import { inviteHeaders } from "@narrativeos/ui/client";
import { withBasePath } from "../app/base-path";

export class ApiError extends Error {
  constructor(message: string, public readonly status: number, public readonly detail?: unknown) {
    super(message);
    this.name = "ApiError";
  }
}

type ClientOptions = { headers?: HeadersInit; errorMessage?: string; inviteAuth?: boolean };

function errorDetail(value: unknown): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map(errorDetail).filter(Boolean).join("；");
  if (!value || typeof value !== "object") return "";
  const detail = value as Record<string, unknown>;
  const message = errorDetail(detail.message ?? detail.msg);
  const context = [
    detail.operation ? `环节：${detail.operation}` : "",
    detail.provider ? `模型：${detail.provider === "mimo" ? "MiMo" : detail.provider === "kimi" ? "Kimi" : detail.provider}` : "",
    detail.diagnostic_id ? `诊断编号：${detail.diagnostic_id}` : "",
  ].filter(Boolean);
  return [message, context.length ? `（${context.join("；")}）` : ""].filter(Boolean).join("");
}

export function createApiClient(prefix: string, options: ClientOptions = {}) {
  async function request(path: string, init: RequestInit = {}): Promise<Response> {
    const headers = new Headers(options.headers);
    new Headers(init.headers).forEach((value, key) => headers.set(key, value));
    if (options.inviteAuth !== false) {
      for (const [key, value] of Object.entries(inviteHeaders())) headers.set(key, value);
    }
    // Let the browser generate the multipart boundary for uploads.
    if (typeof FormData !== "undefined" && init.body instanceof FormData) headers.delete("Content-Type");
    else if (typeof init.body === "string" && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

    const response = await fetch(withBasePath(`${prefix}${path}`), {
      cache: "no-store", ...init, credentials: "include", headers,
    });
    if (!response.ok) {
      const text = await response.text();
      let detail: unknown;
      try {
        const payload = JSON.parse(text) as { detail?: unknown; error?: unknown };
        detail = payload?.detail ?? payload?.error;
      } catch { /* Plain text and upstream HTML errors are handled below. */ }
      const message = errorDetail(detail) || (/^\s*</.test(text) ? "服务器没有返回可解析的错误详情。" : text.trim()) || options.errorMessage || "请求失败，请稍后重试";
      throw new ApiError(`请求失败（HTTP ${response.status}）：${message}`, response.status, detail);
    }
    return response;
  }

  async function json<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await request(path, init);
    const text = await response.text();
    if (!text.trim() && (response.status === 204 || response.status === 205)) return undefined as T;
    try { return JSON.parse(text) as T; }
    catch { throw new ApiError(`服务响应不是有效 JSON（HTTP ${response.status}）`, response.status); }
  }
  return Object.assign(json, {
    blob: async (path: string, init?: RequestInit) => (await request(path, init)).blob(),
  });
}

export const forgeApi = createApiClient("/api/forge");
export const adminApi = createApiClient("/api/forge/admin", { headers: { "X-Forge-Admin-Action": "1" } });
export const paymentsApi = createApiClient("/api/forge/payments");
export const accountApi = createApiClient("/api/account", { inviteAuth: false, headers: { "X-Forge-Auth-Action": "1" } });
