'use client';
import { forwardRef, type ComponentPropsWithoutRef } from 'react';
import { validateUpload, type UploadPolicy } from '../../lib/upload-policy';
import { InlineFeedback } from './feedback';
import { LoadingState } from './state';

export const AssetFileInput = forwardRef<
  HTMLInputElement,
  Omit<ComponentPropsWithoutRef<'input'>, 'type' | 'accept' | 'onChange' | 'onInvalid'> & {
    policy: UploadPolicy;
    resetAfterSelect?: boolean;
    onFileSelected: (file: File) => void | Promise<void>;
    onValidationError: (message: string) => void;
  }
>(function AssetFileInput({ policy, resetAfterSelect = false, onFileSelected, onValidationError, ...props }, ref) {
  return (
    <input
      {...props}
      ref={ref}
      type="file"
      accept={policy.accept}
      onChange={async (event) => {
        // Capture the DOM node before awaiting; React clears event.currentTarget.
        const input = event.currentTarget;
        const file = input.files?.[0];
        if (!file) return;
        const invalid = validateUpload(file, policy);
        if (invalid) {
          input.value = '';
          onValidationError(invalid);
          return;
        }
        onValidationError('');
        try {
          await onFileSelected(file);
        } catch (reason) {
          onValidationError(reason instanceof Error ? reason.message : '上传失败，请重试');
        } finally {
          if (resetAfterSelect) input.value = '';
        }
      }}
    />
  );
});

export function UploadStatus({
  pending,
  error,
  message = '正在上传…',
  className,
}: {
  pending: boolean;
  error?: string;
  message?: string;
  className?: string;
}) {
  if (error)
    return (
      <InlineFeedback variant="inline" className={className}>
        {error}
      </InlineFeedback>
    );
  if (pending)
    return (
      <LoadingState as="p" inline withSpinner className={className}>
        {message}
      </LoadingState>
    );
  return null;
}
