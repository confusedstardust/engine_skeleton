"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { withBasePath } from "../app/base-path";
import { jsonAuthHeaders } from "../app/invite-identity";
export function AdminLink() {
  const [allowed,setAllowed]=useState(false);
  useEffect(()=>{let active=true;fetch(withBasePath('/api/forge/admin/me'),{credentials:'include',headers:jsonAuthHeaders()}).then(r=>{if(active)setAllowed(r.ok);}).catch(()=>{});return()=>{active=false;};},[]);
  return allowed?<Link href="/admin">平台管理</Link>:null;
}
