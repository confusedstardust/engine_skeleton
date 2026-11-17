"use client";

import { createContext, useContext, useEffect, useRef, type ReactNode } from "react";

type Confirm = () => Promise<boolean>;
const LeaveGuard = createContext<{ current: Confirm | null } | null>(null);

export function WorkspaceLeaveGuard({ children }: { children: ReactNode }) {
  const guard = useRef<Confirm | null>(null);
  return <LeaveGuard.Provider value={guard}>{children}</LeaveGuard.Provider>;
}

export function useWorkspaceLeaveConfirmation(confirm: Confirm | null) {
  const guard = useContext(LeaveGuard);
  useEffect(() => {
    if (!guard || !confirm) return;
    guard.current = confirm;
    return () => { guard.current = null; };
  }, [guard, confirm]);
}

export function useLeaveGuard() {
  const guard = useContext(LeaveGuard);
  return {
    confirm: () => guard?.current?.() ?? true,
    hasConfirmation: () => Boolean(guard?.current),
  };
}
