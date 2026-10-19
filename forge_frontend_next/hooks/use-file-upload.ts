'use client';
import { useEffect, useRef, useState } from 'react';
import { validateUpload, type UploadPolicy } from '../lib/upload-policy';

export function useFileUpload() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const lock = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  async function run(file: File, policy: UploadPolicy, upload: (file: File) => Promise<boolean | void>) {
    if (lock.current) return false;
    const invalid = validateUpload(file, policy);
    if (invalid) {
      setError(invalid);
      return false;
    }
    lock.current = true;
    setPending(true);
    setError('');
    try {
      const result = await upload(file);
      if (result === false) {
        if (mounted.current) setError('上传失败，请重试');
        return false;
      }
      return mounted.current;
    } catch (reason) {
      if (mounted.current) setError(reason instanceof Error ? reason.message : '上传失败，请重试');
      return false;
    } finally {
      lock.current = false;
      if (mounted.current) setPending(false);
    }
  }
  return { pending, error, setError, run };
}
