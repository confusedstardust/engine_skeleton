"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { createContext, useContext, useEffect, useState, type MouseEventHandler, type ReactNode } from "react";
import { appBasePath } from "../app/base-path";

const ReturnContext = createContext<string | null>(null);
function labelFor(href: string) {
  const path = href.split("?")[0];
  if (path === "/") return href.includes("workspace=1") ? "创作入口" : "首页";
  if (path === "/history") return "我的作品";
  if (path === "/assets") return "素材库";
  if (path === "/my-assets") return "我的资产";
  if (path === "/recharge") return "创作套餐";
  if (path === "/admin") return "平台管理";
  if (path === "/login") return "登录页";
  if (path.startsWith("/jobs/")) return "作品工作台";
  if (path.startsWith("/practice/")) return "习题";
  if (path.startsWith("/play/")) return "游戏";
  return "上一页";
}

export function NavigationReturnProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const search = useSearchParams().toString();
  const current = (pathname.replace(/\/+$/, "") || "/") + (search ? `?${search}` : "");
  const [previous, setPrevious] = useState<string | null>(null);
  useEffect(() => {
    try {
      const saved = JSON.parse(sessionStorage.getItem("forge-navigation") || "[]") as unknown;
      const stack = Array.isArray(saved) ? saved.filter((item): item is string => typeof item === "string" && item.startsWith("/") && !item.startsWith("//")) : [];
      const index = stack.lastIndexOf(current);
      const next = index >= 0 ? stack.slice(0, index + 1) : [...stack, current];
      if (next.length === 1 && document.referrer) {
        const ref = new URL(document.referrer);
        if (ref.origin === location.origin && (!appBasePath || ref.pathname.startsWith(`${appBasePath}/`))) {
          const source = (ref.pathname.slice(appBasePath.length).replace(/\/+$/, "") || "/") + ref.search;
          if (source !== current) next.unshift(source);
        }
      }
      setPrevious(next.length > 1 ? next[next.length - 2] : null);
      sessionStorage.setItem("forge-navigation", JSON.stringify(next.slice(-50)));
    } catch { setPrevious(null); }
  }, [current]);
  return <ReturnContext.Provider value={previous}>{children}</ReturnContext.Provider>;
}

export function ReturnLink({ fallback = "/", onClick }: { fallback?: string; onClick?: MouseEventHandler<HTMLAnchorElement> }) {
  const previous = useContext(ReturnContext);
  const href = previous || fallback;
  const label = `返回${labelFor(href)}`;
  return <Link className="workspace-back" href={href} aria-label={label} onClick={onClick}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 18-6-6 6-6" /></svg><span>{label}</span></Link>;
}
