'use client';

import { useEffect, useState } from 'react';
import * as ToggleGroup from '@radix-ui/react-toggle-group';
import { adminApi } from '../lib/api-client';
import { useFileUpload } from '../hooks/use-file-upload';
import { htmlResourceUploadPolicy, uploadPolicyHint } from '../lib/upload-policy';
import { Button } from './ui/button';
import { AssetFileInput, UploadStatus } from './ui/file-upload';
import { InlineFeedback } from './ui/feedback';
import { EmptyState, LoadingState } from './ui/state';
import { DataTable } from './ui/table';
import { useToast } from './ui/toast';
import styles from './admin-html-resources.module.css';

type Classification = 'curriculum' | 'stage' | 'subject' | 'grade';
type Resource = { id: string; state: string; payload: { title: string; subject: string; tags: string[]; playUrl: string } };
const labels: Record<Classification, string> = { curriculum: '课程体系', stage: '适用学段', subject: '学科领域', grade: '适用年级' };
const states: Record<string, string> = { saved: '待发布', publishing: '发布待确认', published: '已发布', archived: '已下架' };

export default function AdminHtmlResources() {
  const upload = useFileUpload();
  const notify = useToast();
  const [taxonomy, setTaxonomy] = useState<Record<Classification, string[]> | null>(null);
  const [selected, setSelected] = useState<Record<Classification, string>>({ curriculum: '', stage: '', subject: '', grade: '' });
  const [file, setFile] = useState<File | null>(null);
  const [items, setItems] = useState<Resource[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError('');
    Promise.allSettled([adminApi<Record<Classification, string[]>>('/html-resources/taxonomy', { signal: controller.signal }), adminApi<{ items: Resource[] }>('/html-resources', { signal: controller.signal })])
      .then(([vocabulary, result]) => {
        if (controller.signal.aborted) return;
        if (vocabulary.status === 'fulfilled') setTaxonomy(vocabulary.value);
        if (result.status === 'fulfilled') setItems(result.value.items);
        const failures = [vocabulary, result].filter(value => value.status === 'rejected');
        setError(failures.map(value => value.status === 'rejected' ? String(value.reason?.message || '资源加载失败') : '').join('；'));
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [revision]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || !selected.subject) { upload.setError('请选择资源文件和学科'); return; }
    const form = event.currentTarget;
    const data = new FormData(form);
    data.set('file', file);
    for (const [key, value] of Object.entries(selected)) data.set(key, value);
    const ok = await upload.run(file, htmlResourceUploadPolicy, async () => {
      await adminApi('/html-resources', { method: 'POST', body: data });
    });
    // Also refresh after uncertain publication: saved resources can be retried with the same ID.
    setRevision(value => value + 1);
    if (ok) { form.reset(); setFile(null); notify('资源已发布到教师资源广场', 'success'); }
  }

  async function toggle(item: Resource) {
    setBusy(item.id); setError('');
    try {
      await adminApi(`/html-resources/${item.id}/publication`, { method: item.state === 'published' ? 'DELETE' : 'POST' });
      notify(item.state === 'published' ? '资源已下架' : '资源已发布', 'success');
    } catch (reason) { notify(reason instanceof Error ? reason.message : '操作失败', 'error'); }
    finally { setBusy(''); setRevision(value => value + 1); }
  }

  return <div className={styles.root}>
    <div className={styles.heading}><div><p className={styles.eyebrow}>TEACHER RESOURCES</p><h2>把你的课堂创意带到广场</h2><p>上传 HTML 互动页面，为老师和学生提供可以直接体验的教学资源。</p></div><span className={styles.badge}>HTML / ZIP</span></div>
    <form onSubmit={submit} className={styles.form}>
      <fieldset disabled={upload.pending || loading || !taxonomy} className={styles.fields}>
        <div className={styles.columns}><label><span>资源标题 <span aria-hidden="true">*</span></span><input name="title" required maxLength={160} placeholder="例如：探索行星的公转规律" /></label><label>HTML 入口路径（可选）<input name="entry" maxLength={500} placeholder="自动识别 index.html，也可填 lesson/start.html" /></label></div>
        <label>资源简介<textarea name="summary" maxLength={2000} rows={3} placeholder="介绍学习内容、操作方式或课堂使用建议" /></label>
        <div className={styles.file}><label htmlFor="html-resource-file"><span>上传页面或资源包 <span aria-hidden="true">*</span></span></label><AssetFileInput id="html-resource-file" policy={htmlResourceUploadPolicy} required onFileSelected={setFile} onValidationError={message => { setFile(null); upload.setError(message); }} /><p>{file ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB` : uploadPolicyHint(htmlResourceUploadPolicy)}。有配套资源时，请将 HTML 与资源目录一起压缩为 ZIP，保留相对路径。</p></div>
        <div className={styles.classification}>{taxonomy && (Object.keys(labels) as Classification[]).map(key => <div className={styles.row} key={key}><span id={`resource-${key}`}>{labels[key]}{key === 'subject' ? ' *' : ''}</span><ToggleGroup.Root type="single" value={selected[key]} aria-labelledby={`resource-${key}`} onValueChange={value => setSelected(previous => ({ ...previous, [key]: value }))} className={styles.choices}>{key !== 'subject' && <ToggleGroup.Item value="" asChild><Button variant="unstyled" type="button">未标注</Button></ToggleGroup.Item>}{taxonomy[key].map(value => <ToggleGroup.Item value={value} key={value} asChild><Button variant="unstyled" type="button">{value}</Button></ToggleGroup.Item>)}</ToggleGroup.Root></div>)}</div>
        <div className={styles.actions}><p>学科为必选，其他分类可留空。发布后可在下方管理。</p><Button variant="primary" type="submit" busy={upload.pending} disabled={!file || !selected.subject}>{upload.pending ? '正在上传并发布…' : '上传并发布到广场'}</Button></div>
      </fieldset>
      <UploadStatus pending={upload.pending} error={upload.error} message="正在保存资源并发布到广场，请勿关闭页面…" />
    </form>
    <div className={styles.listHeading}><h3>已上传资源</h3><Button onClick={() => setRevision(value => value + 1)} disabled={loading}>刷新列表</Button></div>
    {error && <InlineFeedback>{error}</InlineFeedback>}
    {loading ? <LoadingState>正在加载资源…</LoadingState> : items.length ? <div className={styles.table}><DataTable className="admin-table"><thead><tr><th>资源</th><th>学科 / 分类</th><th>发布状态</th><th>操作</th></tr></thead><tbody>{items.map(item => <tr key={item.id}><td><strong>{item.payload.title}</strong><small>{item.id}</small></td><td>{[item.payload.subject, ...item.payload.tags].join(' · ')}</td><td>{states[item.state] || item.state}</td><td><div className="admin-actions">{['published', 'publishing'].includes(item.state) && <a className="btn outline" href={item.payload.playUrl} target="_blank" rel="noopener noreferrer">体验资源 ↗</a>}<Button busy={busy === item.id} disabled={!!busy || upload.pending} onClick={() => void toggle(item)}>{item.state === 'published' ? '下架' : '重试发布'}</Button></div></td></tr>)}</tbody></DataTable></div> : !error && <EmptyState>还没有上传资源，发布你的第一个互动课堂。</EmptyState>}
  </div>;
}
