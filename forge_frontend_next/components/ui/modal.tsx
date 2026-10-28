'use client';

import { Button } from './button';
import * as Dialog from './dialog';
import * as AlertDialog from '@radix-ui/react-alert-dialog';
import {
  cloneElement,
  createContext,
  useContext,
  useState,
  useRef,
  useEffect,
  type ReactElement,
  type ReactNode,
} from 'react';

const ModalTitleContext = createContext('');
export function ModalFrame({
  children,
  title,
  onClose,
  busy = false,
}: {
  children: ReactNode;
  title: string;
  onClose: () => void;
  busy?: boolean;
}) {
  return (
    <Dialog.Root
      open
      busy={busy}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <Dialog.Portal>
        <ModalTitleContext.Provider value={title}>
          <Dialog.Overlay asChild>{children}</Dialog.Overlay>
        </ModalTitleContext.Provider>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
export function ModalBody({ children }: { children: ReactElement<{ children?: ReactNode }> }) {
  const title = useContext(ModalTitleContext);
  return (
    <Dialog.Content asChild aria-describedby={undefined}>
      {cloneElement(
        children,
        {},
        <>
          <Dialog.Title className="sr-only">{title}</Dialog.Title>
          {children.props.children}
        </>,
      )}
    </Dialog.Content>
  );
}

export function ConfirmDialog({
  error,
  open,
  title,
  description,
  busy = false,
  onCancel,
  onConfirm,
}: {
  error?: string;
  open: boolean;
  title: string;
  description: string;
  busy?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <AlertDialog.Root
      open={open}
      onOpenChange={(value) => {
        if (!value && !busy) onCancel();
      }}
    >
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="radix-confirm-overlay" />
        <AlertDialog.Content
          className="asset-confirm-dialog radix-confirm-content"
          onEscapeKeyDown={(event) => {
            if (busy) event.preventDefault();
          }}
        >
          <AlertDialog.Title>{title}</AlertDialog.Title>
          <AlertDialog.Description>{description}</AlertDialog.Description>
          {error && <p role="alert" className="error">{error}</p>}
          <div className="asset-confirm-actions">
            <AlertDialog.Cancel asChild>
              <Button variant="outline" busy={Boolean(busy)}>
                取消
              </Button>
            </AlertDialog.Cancel>
            <Button variant="primary" busy={Boolean(busy)} onClick={onConfirm}>
              {busy ? '正在处理…' : '确认'}
            </Button>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
}

const ConfirmationContext = createContext<(message: string) => Promise<boolean>>(() => Promise.resolve(false));
export const useConfirmation = () => useContext(ConfirmationContext);
export function ConfirmationProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState<string | null>(null);
  const pending = useRef<((result: boolean) => void) | null>(null);
  useEffect(
    () => () => {
      pending.current?.(false);
    },
    [],
  );
  function finish(result: boolean) {
    pending.current?.(result);
    pending.current = null;
    setMessage(null);
  }
  function confirm(description: string) {
    pending.current?.(false);
    setMessage(description);
    return new Promise<boolean>((resolve) => {
      pending.current = resolve;
    });
  }
  return (
    <ConfirmationContext.Provider value={confirm}>
      {children}
      <ConfirmDialog
        open={message !== null}
        title="请确认"
        description={message || ''}
        onCancel={() => finish(false)}
        onConfirm={() => finish(true)}
      />
    </ConfirmationContext.Provider>
  );
}
