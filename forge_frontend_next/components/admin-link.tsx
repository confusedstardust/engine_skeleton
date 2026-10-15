"use client";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { withBasePath } from "../app/base-path";
import { jsonAuthHeaders } from "../app/invite-identity";
export function AdminLink({ children, onClick }: { children?: ReactNode; onClick?: () => void } = {}) {
  const [allowed,setAllowed]=useState(false);
  useEffect(()=>{let active=true;fetch(withBasePath('/api/forge/admin/me'),{credentials:'include',headers:jsonAuthHeaders()}).then(r=>{if(active)setAllowed(r.ok);}).catch(()=>{});return()=>{active=false;};},[]);
  return allowed?<Link href="/admin" onClick={onClick}>{children ?? "平台管理"}</Link>:null;
}
