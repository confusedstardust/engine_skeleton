"use client";

import { Suspense, type ReactNode } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { LoadingState } from "../../components/ui/state";
import { PracticeShell } from "./practice-shell";
import { agentRoute } from "../../lib/workspace-routes";

/**
 * App Router layout stays mounted between /practice and /practice/chat/:id.
 * Sidebar, header, resizer and authenticated identity are preserved; only
 * the conversation data changes. Non-studio routes render their own pages.
 */
function RoutedPractice({ children }: { children: ReactNode }) {
  const path = usePathname();
  const query = useSearchParams();
  const conversationMatch = /^\/practice\/chat\/([a-f0-9]{32})\/?$/.exec(path);
  const isGeneral = path === "/practice" || path === "/practice/";
  if (!agentRoute(path.replace(/\/+$/, ""))) return <>{children}</>;
  const work = isGeneral ? query.get("work") : null;
  const workspaceScope = conversationMatch ? "chat:" + conversationMatch[1]
    : work && /^[a-f0-9]{32}$/.test(work) ? work : "general";
  // Intentionally no key: React reuses the entire workspace across chats.
  return <PracticeShell workspaceScope={workspaceScope}
    conversationId={conversationMatch?.[1]} />;
}

export default function PracticeLayout({ children }: { children: ReactNode }) {
  return <Suspense fallback={<LoadingState>正在打开互动学习工作台…</LoadingState>}>
    <RoutedPractice>{children}</RoutedPractice>
  </Suspense>;
}
