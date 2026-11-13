'use client';

import { useEffect, useRef, useState, type ReactNode } from 'react';
import HtmlResourceTags, { emptyClassification, type Classification, type ResourceTaxonomy } from './html-resource-tags';
import * as Dialog from './ui/dialog';
import { DialogHeader } from './ui/dialog-header';
import { DialogActions } from './ui/dialog-actions';
import { adminApi } from '../lib/api-client';
import { useFileUpload } from '../hooks/use-file-upload';
import { htmlResourceUploadPolicy, imageUploadPolicy, uploadPolicyHint } from '../lib/upload-policy';
import { Button } from './ui/button';
import { AssetFileInput, UploadStatus } from './ui/file-upload';
import { InlineFeedback } from './ui/feedback';
import { EmptyState, LoadingState } from './ui/state';
import { DataTable } from './ui/table';
import { useToast } from './ui/toast';
import styles from './admin-html-resources.module.css';

export type HtmlResource = { created_at?: string; entry?: string; metadata_sync_error?: string; id: string; state: string; classification: Classification; cover_status?: string; cover_error?: string; cover_failed_assets?: number; payload: { featured?: boolean; summary?: string | null; title: string; subject: string; tags: string[]; playUrl: string; coverUrl?: string } };
type Resource = HtmlResource;
export type HtmlResourceListControls = { items: HtmlResource[]; loading: boolean; error: string; busy: boolean; revision: number; onEdit: (item: HtmlResource) => void; onFeature: (item: HtmlResource) => void; onPublication: (item: HtmlResource) => void };
const states: Record<string, string> = { saved: '待发布', publishing: '发布待确认', published: '已发布', archived: '已下架' };

export default function AdminHtmlResources({ renderList }: { renderList?: (controls: HtmlResourceListControls) => ReactNode } = {}) {
  const upload = useFileUpload();
  const notify = useToast();
  const [taxonomy, setTaxonomy] = useState<ResourceTaxonomy | null>(null);
  const [selected, setSelected] = useState<Classification>(emptyClassification);
  const [editing, setEditing] = useState<Resource | null>(null);
  const [editTags, setEditTags] = useState<Classification>(emptyClassification);
  const [editError, setEditError] = useState('');
  const [editTitle, setEditTitle] = useState('');
  const [editSummary, setEditSummary] = useState('');
  const [editEntry, setEditEntry] = useState('');
  const [editFeatured, setEditFeatured] = useState(false);
  const [replacement, setReplacement] = useState<File | null>(null);
  const [coverFile, setCoverFile] = useState<File | null>(null);
  const [coverPreview, setCoverPreview] = useState('');
  const coverPolicy = { ...imageUploadPolicy, maxBytes: 5 * 1024 * 1024 };
  useEffect(() => () => { if (coverPreview) URL.revokeObjectURL(coverPreview); }, [coverPreview]);
  function openEditor(item: Resource) {
    setEditing(item); setEditTags(item.classification); setEditError('');
    setEditTitle(item.payload.title); setEditSummary(item.payload.summary || '');
    setEditEntry(item.entry || ''); setEditFeatured(!!item.payload.featured);
    setReplacement(null); setCoverFile(null); setCoverPreview('');
  }
  async function toggleFeatured(item: Resource) {
    setBusy(item.id);
    try {
      await adminApi(`/html-resources/${item.id}/featured`, { method: 'PATCH', body: JSON.stringify({ featured: !item.payload.featured }) });
      notify(item.payload.featured ? '已取消精选' : '已设为精选，轮播展示最近更新的 8 个已发布精选案例', 'success');
    } catch (reason) { notify(reason instanceof Error ? reason.message : '精选设置失败', 'error'); }
    finally { setBusy(''); setRevision(value => value + 1); }
  }
  const [file, setFile] = useState<File | null>(null);
  const [items, setItems] = useState<Resource[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState('');
  const pollCount = useRef(0);
  useEffect(() => {
    if (!items.some(item => ['pending', 'generating'].includes(item.cover_status || '')) || pollCount.current >= 45) return;
    const timer = setTimeout(() => {
      if (document.visibilityState === 'visible') { pollCount.current++; setRevision(value => value + 1); }
    }, 3000);
    return () => clearTimeout(timer);
  }, [items, revision]);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError('');
    Promise.allSettled([adminApi<ResourceTaxonomy>('/html-resources/taxonomy', { signal: controller.signal }), adminApi<{ items: Resource[] }>('/html-resources', { signal: controller.signal })])
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
    if (!file || !selected.subject.length) { upload.setError('请选择资源文件和学科'); return; }
    const form = event.currentTarget;
    const data = new FormData(form);
    data.set('file', file);
    for (const [key, value] of Object.entries(selected)) data.set(key, JSON.stringify(value));
    const ok = await upload.run(file, htmlResourceUploadPolicy, async () => {
      await adminApi('/html-resources', { method: 'POST', body: data });
    });
    // Also refresh after uncertain publication: saved resources can be retried with the same ID.
    setRevision(value => value + 1);
    if (ok) { form.reset(); setFile(null); pollCount.current = 0; notify('资源已发布，正在自动生成封面', 'success'); }
  }

  async function toggle(item: Resource) {
    setBusy(item.id); setError('');
    try {
      await adminApi(`/html-resources/${item.id}/publication`, { method: item.state === 'published' ? 'DELETE' : 'POST' });
      notify(item.state === 'published' ? '资源已下架' : '资源已发布', 'success');
    } catch (reason) { notify(reason instanceof Error ? reason.message : '操作失败', 'error'); }
    finally { setBusy(''); setRevision(value => value + 1); }
  }

  async function saveResource(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editing || !editTags.subject.length) return;
    setBusy(editing.id); setEditError('');
    let detailsSaved = false;
    try {
      const data = new FormData();
      data.set('title', editTitle); data.set('summary', editSummary); data.set('entry', editEntry);
      data.set('classification', JSON.stringify(editTags)); data.set('featured', String(editFeatured));
      if (replacement) data.set('file', replacement);
      const saved = await adminApi<Resource>(`/html-resources/${editing.id}`, { method: 'PATCH', body: data });
      detailsSaved = true;
      setEditing(saved); setReplacement(null);
      if (coverFile) {
        const cover = new FormData(); cover.set('file', coverFile);
        const result = await adminApi<{ cover_status: string; cover_error?: string }>(`/html-resources/${editing.id}/cover`, { method: 'POST', body: cover });
        if (result.cover_status === 'sync_failed') throw new Error(result.cover_error || '封面已保存，广场同步待重试');
      }
      notify('资源设置已保存', 'success'); setEditing(null);
    } catch (reason) {
      setEditError((detailsSaved ? '资源信息已保存；封面处理未完成，可重试保存。' : '') + (reason instanceof Error ? reason.message : '保存失败'));
    } finally { setBusy(''); setRevision(value => value + 1); }
  }

  return <div className={styles.root}>
    <div className={styles.heading}><div><p className={styles.eyebrow}>TEACHER RESOURCES</p><h2>把你的课堂创意带到广场</h2><p>上传 HTML 互动页面，为老师和学生提供可以直接体验的教学资源。</p></div><span className={styles.badge}>HTML / ZIP</span></div>
    <form onSubmit={submit} className={styles.form}>
      <fieldset disabled={upload.pending || loading || !taxonomy} className={styles.fields}>
        <div className={styles.columns}><label><span>资源标题 <span aria-hidden="true">*</span></span><input name="title" required maxLength={160} placeholder="例如：探索行星的公转规律" /></label><label>HTML 入口路径（可选）<input name="entry" maxLength={500} placeholder="自动识别 index.html，也可填 lesson/start.html" /></label></div>
        <label>资源简介<textarea name="summary" maxLength={2000} rows={3} placeholder="介绍学习内容、操作方式或课堂使用建议" /></label>
        <div className={styles.file}><label htmlFor="html-resource-file"><span>上传页面或资源包 <span aria-hidden="true">*</span></span></label><AssetFileInput id="html-resource-file" policy={htmlResourceUploadPolicy} required onFileSelected={setFile} onValidationError={message => { setFile(null); upload.setError(message); }} /><p>{file ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB` : uploadPolicyHint(htmlResourceUploadPolicy)}。有配套资源时，请将 HTML 与资源目录一起压缩为 ZIP，保留相对路径。</p></div>
        {taxonomy && <HtmlResourceTags id="upload-tags" taxonomy={taxonomy} value={selected} onChange={setSelected} />}
        <div className={styles.actions}><p>学科至少选一个，所有分类均可多选或自定义。发布后仍可修改。</p><Button variant="primary" type="submit" busy={upload.pending} disabled={!file || !selected.subject.length}>{upload.pending ? '正在上传并发布…' : '上传并发布到广场'}</Button></div>
      </fieldset>
      <UploadStatus pending={upload.pending} error={upload.error} message="正在保存资源并发布到广场，请勿关闭页面…" />
    </form>
    <div className={styles.listHeading}><h3>{renderList ? "教学资源" : "已上传资源"}</h3><Button onClick={() => setRevision(value => value + 1)} disabled={loading}>刷新列表</Button></div>
    {renderList ? renderList({ items, loading, error, busy: !!busy || upload.pending || !taxonomy, revision, onEdit: openEditor, onFeature: item => void toggleFeatured(item), onPublication: item => void toggle(item) }) : <>
    {error && <InlineFeedback>{error}</InlineFeedback>}
    {loading ? <LoadingState>正在加载资源…</LoadingState> : items.length ? <div className={styles.table}><DataTable className="admin-table"><thead><tr><th>资源 · 点击编辑</th><th>学科 / 分类</th><th>发布状态</th><th>操作</th></tr></thead><tbody>{items.map(item => <tr key={item.id}>
      <td><button className={styles.resourceButton} disabled={!!busy || upload.pending || !taxonomy} onClick={() => openEditor(item)} aria-label={`编辑资源：${item.payload.title}`}>
        {item.payload.coverUrl ? <img className={styles.coverThumb} src={item.payload.coverUrl} alt="" loading="lazy" /> : <span className={styles.noCover}>暂无封面</span>}
        <span><strong>{item.payload.title}</strong><small>{item.id}</small><em>编辑资源 ↗</em></span></button>
        {['pending', 'generating'].includes(item.cover_status || '') && <small role="status">封面生成中…</small>}
        {(item.cover_error || item.metadata_sync_error) && <small className={styles.coverError}>{item.metadata_sync_error || item.cover_error}</small>}
      </td><td>{[...new Set([item.payload.subject, ...item.payload.tags])].join(' · ')}</td>
      <td>{states[item.state] || item.state}{item.payload.featured && <small className={styles.featuredBadge}>精选</small>}</td>
      <td><div className="admin-actions"><Button disabled={!!busy || upload.pending} onClick={() => void toggleFeatured(item)}>{item.payload.featured ? '取消精选' : '设为精选'}</Button>{['published', 'publishing'].includes(item.state) && <a className="btn outline" href={item.payload.playUrl} target="_blank" rel="noopener noreferrer">体验资源 ↗</a>}<Button busy={busy === item.id} disabled={!!busy || upload.pending} onClick={() => void toggle(item)}>{item.state === 'published' ? '下架' : '重试发布'}</Button></div></td>
    </tr>)}</tbody></DataTable></div> : !error && <EmptyState>还没有上传资源，发布你的第一个互动课堂。</EmptyState>}
    </>}
    <Dialog.Root open={!!editing} busy={!!busy} onOpenChange={open => { if (!open) setEditing(null); }}>
      <Dialog.Surface overlayClassName="radix-confirm-overlay" className={`admin-detail ${styles.editDialog}`} aria-describedby={undefined}>
        <DialogHeader dialogTitle title="编辑课堂资源" subtitle="基本信息、封面与分类，在这里统一管理" onClose={() => setEditing(null)} busy={!!busy} />
        {editing && <form onSubmit={saveResource} className={styles.editForm}><fieldset disabled={!!busy} className={styles.fields}>
          <div className={styles.editorTop}>
            <div className={styles.coverEditor}><label htmlFor="edit-cover">资源封面</label>
              {coverPreview || editing.payload.coverUrl ? <img src={coverPreview || editing.payload.coverUrl} alt="资源封面预览" /> : <div className={styles.noCover}>暂无封面</div>}
              <AssetFileInput id="edit-cover" policy={coverPolicy} onFileSelected={file => { setCoverFile(file); setCoverPreview(URL.createObjectURL(file)); }} onValidationError={message => { if (message) { setCoverFile(null); setCoverPreview(''); setEditError(message); } }} />
              <small>选择图片即可更换，保存后生效。建议 16:9，最大 5 MB。</small>
            </div>
            <div className={styles.editorInfo}><label>资源标题 *<input required maxLength={160} value={editTitle} onChange={event => setEditTitle(event.target.value)} /></label>
              <label>资源简介<textarea maxLength={2000} rows={4} value={editSummary} onChange={event => setEditSummary(event.target.value)} /></label>
              <Button type="button" aria-pressed={editFeatured} className={styles.featureToggle} onClick={() => setEditFeatured(value => !value)}>{editFeatured ? '★ 已设为精选' : '☆ 设为精选案例'}</Button>
              <small>轮播展示最近更新的 8 个已发布精选案例；下架资源不会展示。</small>
            </div>
          </div>
          <details className={styles.packageDetails}><summary>更新资源文件与 HTML 入口（可选）</summary>
            <label>HTML 入口路径<input maxLength={500} value={editEntry} onChange={event => setEditEntry(event.target.value)} placeholder="例如 lesson/index.html" /></label>
            <label>替换 HTML / ZIP 资源包<AssetFileInput policy={htmlResourceUploadPolicy} onFileSelected={file => { setReplacement(file); setEditEntry(''); }} onValidationError={message => { if (message) { setReplacement(null); setEditError(message); } }} /></label>
            <p>{replacement ? `待替换：${replacement.name}` : '不选择文件则保留原资源包。替换时请包含全部配套文件，留空入口会自动识别。'}</p>
          </details>
          <div><h3 className={styles.sectionTitle}>适用范围与标签</h3>{taxonomy && <HtmlResourceTags id="edit-tags" taxonomy={taxonomy} value={editTags} onChange={setEditTags} />}</div>
          {editError && <InlineFeedback>{editError}</InlineFeedback>}
          <DialogActions className={styles.editorFooter}><Button onClick={() => setEditing(null)}>取消</Button><Button variant="primary" type="submit" busy={!!busy} disabled={!editTags.subject.length || !editTitle.trim()}>保存设置</Button></DialogActions>
        </fieldset></form>}
      </Dialog.Surface>
    </Dialog.Root>
  </div>;
}
