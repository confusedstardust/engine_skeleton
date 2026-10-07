"use client";

import * as Dialog from "@radix-ui/react-dialog";
import * as AlertDialog from "@radix-ui/react-alert-dialog";
import { Children, isValidElement, cloneElement, createContext, useContext, useState, useRef, useEffect, type ReactElement, type ReactNode } from "react";

export function ModalFrame({ children, title, onClose }: { children: ReactElement<{ children?: ReactNode }>; title: string; onClose: () => void }) {
  const returnFocus = useRef<HTMLElement | null>(typeof document !== "undefined" && document.activeElement instanceof HTMLElement ? document.activeElement : null);
  const content = Children.map(children.props.children, (child) => {
    if (isValidElement<{ children?: ReactNode }>(child) && child.type === "section") {
      return <Dialog.Content asChild aria-describedby={undefined} onCloseAutoFocus={(event) => { event.preventDefault(); if (returnFocus.current?.isConnected) returnFocus.current.focus({ preventScroll: true }); }}>{cloneElement(child, {}, <><Dialog.Title className="sr-only">{title}</Dialog.Title>{child.props.children}</>)}</Dialog.Content>;
    }
    return child;
  });
  return <Dialog.Root open onOpenChange={(open) => { if (!open) onClose(); }}><Dialog.Portal><Dialog.Overlay asChild>{cloneElement(children, {}, content)}</Dialog.Overlay></Dialog.Portal></Dialog.Root>;
}

export function ConfirmDialog({ open, title, description, busy = false, onCancel, onConfirm }: { open: boolean; title: string; description: string; busy?: boolean; onCancel: () => void; onConfirm: () => void }) {
  return <AlertDialog.Root open={open} onOpenChange={(value) => { if (!value && !busy) onCancel(); }}><AlertDialog.Portal>
    <AlertDialog.Overlay className="radix-confirm-overlay" />
    <AlertDialog.Content className="asset-confirm-dialog radix-confirm-content" onEscapeKeyDown={(event) => { if (busy) event.preventDefault(); }}>
      <AlertDialog.Title>{title}</AlertDialog.Title><AlertDialog.Description>{description}</AlertDialog.Description>
      <div className="asset-confirm-actions"><AlertDialog.Cancel asChild><button className="btn outline" disabled={busy}>取消</button></AlertDialog.Cancel><button className="btn primary" disabled={busy} onClick={onConfirm}>{busy ? "正在处理…" : "确认"}</button></div>
    </AlertDialog.Content>
  </AlertDialog.Portal></AlertDialog.Root>;
}

const ConfirmationContext = createContext<(message: string) => Promise<boolean>>(() => Promise.resolve(false));
export const useConfirmation = () => useContext(ConfirmationContext);
export function ConfirmationProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState<string | null>(null);
  const pending = useRef<((result: boolean) => void) | null>(null);
  useEffect(() => () => { pending.current?.(false); }, []);
  function finish(result: boolean) { pending.current?.(result); pending.current = null; setMessage(null); }
  function confirm(description: string) { pending.current?.(false); setMessage(description); return new Promise<boolean>((resolve) => { pending.current = resolve; }); }
  return <ConfirmationContext.Provider value={confirm}>{children}<ConfirmDialog open={message !== null} title="请确认" description={message || ""} onCancel={() => finish(false)} onConfirm={() => finish(true)} /></ConfirmationContext.Provider>;
}
