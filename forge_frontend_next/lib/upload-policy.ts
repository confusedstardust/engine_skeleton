export type UploadPolicy = { extensions: readonly string[]; accept: string; formats: string; maxBytes: number };
const maxBytes = 30 * 1024 * 1024;
export const imageUploadPolicy: UploadPolicy = {
  extensions: ['png', 'jpg', 'jpeg', 'webp'],
  accept: '.png,.jpg,.jpeg,.webp',
  formats: 'PNG、JPEG、WebP',
  maxBytes,
};
export const musicUploadPolicy: UploadPolicy = {
  extensions: ['mp3', 'wav', 'ogg'],
  accept: '.mp3,.wav,.ogg',
  formats: 'MP3、WAV、OGG',
  maxBytes,
};
// The admin endpoint additionally accepts M4A; workspace uploads do not.
export const adminMusicUploadPolicy: UploadPolicy = {
  ...musicUploadPolicy,
  extensions: [...musicUploadPolicy.extensions, 'm4a'],
  accept: '.mp3,.wav,.ogg,.m4a',
  formats: 'MP3、WAV、OGG、M4A',
};
export function uploadPolicyHint(policy: UploadPolicy) {
  return `${policy.formats} · 最大 ${policy.maxBytes / 1024 / 1024} MB`;
}
export function validateUpload(file: Pick<File, 'name' | 'size'>, policy: UploadPolicy): string | null {
  if (!file.size) return '文件不能为空';
  if (file.size > policy.maxBytes) return `文件不能超过 ${policy.maxBytes / 1024 / 1024} MB`;
  const extension = file.name.includes('.') ? file.name.split('.').pop()!.toLowerCase() : '';
  if (!policy.extensions.includes(extension)) return `请选择 ${policy.formats} 格式的文件`;
  return null;
}
