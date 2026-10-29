'use client';
import { Button } from '../ui/button';
import { DialogActions } from '../ui/dialog-actions';
import type { ReactNode } from 'react';

export function AssetSourceActions({ busy, onUpload, onLibrary }: {
  busy?: boolean;
  onUpload: () => void;
  onLibrary: () => void;
}) {
  return <div className="asset-modal-source-actions">
    <Button variant="outline" className="asset-modal-upload-button" type="button" busy={Boolean(busy)} onClick={onUpload}>{busy ? '正在处理…' : '上传图片'}</Button>
    <Button variant="outline" className="asset-modal-upload-button" type="button" busy={Boolean(busy)} onClick={onLibrary}>从素材库选择</Button>
  </div>;
}

export function AssetDialogActions({ children, busy, onClose }: {
  children?: ReactNode;
  busy?: boolean;
  onClose: () => void;
}) {
  return <DialogActions as="footer" className="asset-modal-actions">
    {children}
    <Button variant="primary" type="button" busy={Boolean(busy)} onClick={onClose}>关闭</Button>
  </DialogActions>;
}
