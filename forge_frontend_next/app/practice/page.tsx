"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { LoadingState } from "../../components/ui/state";
import { PracticeShell } from "./practice-shell";

/** Legacy work deep links remain supported alongside durable chat routes. */
function ScopedPracticePage() {
  const params = useSearchParams();
  const workId = params.get("work");
  const workspaceScope = workId && /^[a-f0-9]{32}$/.test(workId) ? workId : "general";
  return <PracticeShell key={workspaceScope} workspaceScope={workspaceScope} />;
}
export default function PracticePage() {
  return <Suspense fallback={<LoadingState>正在打开互动学习工作台…</LoadingState>}>
    <ScopedPracticePage />
  </Suspense>;
}
