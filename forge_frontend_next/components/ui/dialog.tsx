'use client';
import * as Primitive from '@radix-ui/react-dialog';
import { createContext, forwardRef, useContext, useRef, type ComponentPropsWithoutRef } from 'react';

const BusyContext = createContext(false);
export function Root({
  busy = false,
  onOpenChange,
  ...props
}: ComponentPropsWithoutRef<typeof Primitive.Root> & { busy?: boolean }) {
  return (
    <BusyContext.Provider value={busy}>
      <Primitive.Root
        {...props}
        onOpenChange={(open) => {
          if (!busy) onOpenChange?.(open);
        }}
      />
    </BusyContext.Provider>
  );
}
export const Content = forwardRef<HTMLDivElement, ComponentPropsWithoutRef<typeof Primitive.Content>>(
  function DialogContent(
    { onEscapeKeyDown, onPointerDownOutside, onInteractOutside, onCloseAutoFocus, ...props },
    ref,
  ) {
    const busy = useContext(BusyContext);
    const returnFocus = useRef<HTMLElement | null>(
      typeof document !== 'undefined' && document.activeElement instanceof HTMLElement ? document.activeElement : null,
    );
    return (
      <Primitive.Content
        {...props}
        ref={ref}
        onEscapeKeyDown={(event) => {
          onEscapeKeyDown?.(event);
          if (busy) event.preventDefault();
        }}
        onPointerDownOutside={(event) => {
          onPointerDownOutside?.(event);
          if (busy || (event.target instanceof Element && event.target.closest(".app-toast"))) event.preventDefault();
        }}
        onInteractOutside={(event) => {
          onInteractOutside?.(event);
          if (busy || (event.target instanceof Element && event.target.closest(".app-toast"))) event.preventDefault();
        }}
        onCloseAutoFocus={(event) => {
          onCloseAutoFocus?.(event);
          if (!event.defaultPrevented && returnFocus.current?.isConnected) {
            event.preventDefault();
            returnFocus.current.focus({ preventScroll: true });
          }
        }}
      />
    );
  },
);
export const { Portal, Overlay, Title, Description, Close, Trigger } = Primitive;

export function Surface({
  overlayClassName = 'radix-confirm-overlay',
  ...props
}: ComponentPropsWithoutRef<typeof Content> & { overlayClassName?: string }) {
  return (
    <Portal>
      <Overlay className={overlayClassName} />
      <Content {...props} />
    </Portal>
  );
}
