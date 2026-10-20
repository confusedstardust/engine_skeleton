"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import { createPortal } from "react-dom";

type ToastProps = {
  message: string;
  onClose: () => void;
  tone?: "info" | "success" | "error";
  duration?: number;
};

/** Transient operation feedback. Validation stays in forms; confirmation uses dialogs. */
export function Toast({ message, onClose, tone = "info", duration = tone === "error" ? 8000 : 4000 }: ToastProps) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => { setMounted(true); }, []);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    if (!message || duration <= 0) return;
    const timer = window.setTimeout(() => closeRef.current(), duration);
    return () => window.clearTimeout(timer);
  }, [message, duration, tone]);
  if (!message || !mounted) return null;
  return createPortal(<div className="app-toast" data-tone={tone} role={tone === "error" ? "alert" : "status"} aria-live={tone === "error" ? "assertive" : "polite"} aria-atomic="true">
    <span className="app-toast-icon" aria-hidden="true">{tone === "success" ? "✓" : tone === "error" ? "!" : "i"}</span>
    <span className="app-toast-message">{message}</span>
    <button type="button" onClick={onClose} aria-label="关闭提示">×</button>
  </div>, document.body);
}

export type Notify = (message: string, tone?: "info" | "success" | "error", duration?: number) => void;
const ToastContext = createContext<Notify>(() => {});

/** One host survives form refreshes and renders only the latest operation feedback. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [notice, setNotice] = useState<{ id: number; message: string; tone: "info" | "success" | "error"; duration?: number } | null>(null);
  const sequence = useRef(0);
  const notify = useCallback<Notify>((message, tone = "info", duration) => {
    if (message) setNotice({ id: ++sequence.current, message, tone, duration });
  }, []);
  return <ToastContext.Provider value={notify}>{children}{notice && <Toast key={notice.id} {...notice} onClose={() => setNotice(null)} />}</ToastContext.Provider>;
}
export const useToast = () => useContext(ToastContext);

export function useErrorToast(message: string, suppressed = false) {
  const notify = useToast();
  const previous = useRef("");
  useEffect(() => {
    if (!message) { previous.current = ""; return; }
    if (!suppressed && previous.current !== message) {
      previous.current = message;
      notify(message, "error");
    }
  }, [message, suppressed, notify]);
}
