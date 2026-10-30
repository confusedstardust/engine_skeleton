'use client';
import { DialogHeader } from './dialog-header';
import type { ReactNode, Ref, HTMLAttributes } from 'react';
import { ModalFrame, ModalBody } from './modal';

export function ContentDialog({ title, subtitle, onClose, busy, children, footer, notice,
  layerClassName = 'content-dialog-layer', className, headerClassName = 'asset-modal-head',
  bodyClassName, bodyProps, panelRef, closeInHeader = true,
}: {
  title: string;
  subtitle?: ReactNode;
  onClose: () => void;
  busy?: boolean;
  children: ReactNode;
  footer?: ReactNode;
  notice?: ReactNode;
  layerClassName?: string;
  className?: string;
  headerClassName?: string;
  bodyClassName?: string;
  bodyProps?: HTMLAttributes<HTMLDivElement>;
  panelRef?: Ref<HTMLElement>;
  closeInHeader?: boolean;
}) {
  return <ModalFrame title={title} onClose={onClose} busy={busy}>
    <div className={`content-dialog-overlay ${layerClassName}`}>
      <ModalBody><section className={className} ref={panelRef}>
        <DialogHeader title={title} eyebrow={subtitle} className={headerClassName} busy={busy} onClose={closeInHeader ? onClose : undefined} />
        {notice}
        <div {...bodyProps} className={bodyClassName}>{children}</div>
        {footer}
      </section></ModalBody>
    </div>
  </ModalFrame>;
}
