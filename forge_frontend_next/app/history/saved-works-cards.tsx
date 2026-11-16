"use client";

import Link from "next/link";
import { useState, type Dispatch, type SetStateAction } from "react";
import { CollectionCard } from "@narrativeos/ui/collection-card";
import { ImagePreview } from "../../components/ui/image-preview";
import { Button } from "../../components/ui/button";
import { useToast } from "../../components/ui/toast";
import { ConfirmDialog, ModalBody, ModalFrame } from "../../components/ui/modal";
import { workApi, type SavedWork, type PublicationForm, type SharedWork } from "../../lib/work-api";
import WorkPublishDialog from "../practice/work-publish-dialog";
import WorkShareDialog from "../practice/work-share-dialog";
import { withBasePath } from "../base-path";

function displayTime(value?: string): string {
  if (!value) return "未知时间";
  const dt = new Date(value);
  return Number.isNaN(dt.getTime()) ? "未知时间" : dt.toLocaleString("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

function workView(work: SavedWork) {
  return {
    workId: work.id, currentVersionId: work.current_version_id,
    title: work.title, summary: work.summary, subject: work.subject,
    grade: work.grade, tags: work.tags, coverVariant: work.cover_variant,
  };
}

function isPublic(work: SavedWork) {
  return work.publication_status === "published";
}

export default function SavedWorksCards({
  works, setWorks,
}: {
  works: SavedWork[];
  setWorks: Dispatch<SetStateAction<SavedWork[]>>;
}) {
  const notify = useToast();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [dialogError, setDialogError] = useState("");
  const [rename, setRename] = useState<SavedWork | null>(null);
  const [name, setName] = useState("");
  const [cover, setCover] = useState<SavedWork | null>(null);
  const [publish, setPublish] = useState<SavedWork | null>(null);
  const [revoke, setRevoke] = useState<SavedWork | null>(null);
  const [remove, setRemove] = useState<SavedWork | null>(null);
  const [sharePrompt, setSharePrompt] = useState<SavedWork | null>(null);
  const [shared, setShared] = useState<SharedWork | null>(null);

  const working = busyId !== null;
  function startRename(work: SavedWork) {
    setDialogError(""); setRename(work); setName(work.title);
  }
  async function perform(work: SavedWork, operation: () => Promise<void>) {
    if (working) return;
    setBusyId(work.id); setDialogError("");
    try {
      await operation();
      notify("操作已完成", "success");
    } catch (error) {
      const text = error instanceof Error ? error.message : "作品操作失败，请稍后重试";
      setDialogError(text);
      notify(text, "error");
    } finally {
      setBusyId(null);
    }
  }
  async function openShare(work: SavedWork) {
    if (!isPublic(work)) {
      setSharePrompt(work);
      return;
    }
    await perform(work, async () => {
      setShared(await workApi.share(work.id));
    });
  }
  async function saveRename() {
    if (!rename || !name.trim() || name.trim().length > 160) return;
    await perform(rename, async () => {
      const response = await workApi.update(rename.id, { title: name.trim() });
      setWorks(current => current.map(item => item.id === rename.id ? response.work : item));
      setRename(null);
    });
  }
  async function saveCover(payload: PublicationForm) {
    if (!cover) return;
    await perform(cover, async () => {
      const response = await workApi.update(cover.id, { cover_variant: payload.cover_variant || "preview" });
      setWorks(current => current.map(item => item.id === cover.id ? response.work : item));
      setCover(null);
    });
  }
  async function submitPublish(payload: PublicationForm) {
    if (!publish) return;
    await perform(publish, async () => {
      const result = await workApi.publish(publish.id, payload);
      if (!result.published) throw new Error("广场尚未确认发布，请重试");
      const fresh = await workApi.get(publish.id);
      setWorks(current => current.map(item => item.id === publish.id ? fresh.work : item));
      setPublish(null);
    });
  }
  async function confirmRevoke() {
    if (!revoke) return;
    await perform(revoke, async () => {
      await workApi.unpublish(revoke.id);
      const fresh = await workApi.get(revoke.id);
      setWorks(current => current.map(item => item.id === revoke.id ? fresh.work : item));
      setRevoke(null);
    });
  }
  async function confirmDelete() {
    if (!remove) return;
    await perform(remove, async () => {
      // Never orphan an active public link: de-index before deleting files.
      if (remove.publication_status === "published" ||
          remove.publication_status === "unpublish_pending") {
        await workApi.unpublish(remove.id);
      }
      await workApi.remove(remove.id);
      setWorks(current => current.filter(item => item.id !== remove.id));
      setRemove(null);
    });
  }

  return <>
    {works.map(work => {
      const current = work.versions.find(version => version.id === work.current_version_id);
      const player = `/practice/works/${work.id}/?owner=1`;
      const editHref = `/practice/?work=${work.id}`;
      const unavailable = working || work.publication_status === "publishing";
      const publicOrRevoking = work.publication_status === "published" ||
        work.publication_status === "unpublish_pending";
      return <CollectionCard className="history-row" key={`nar:${work.id}`}
        menuLabel={`作品操作：${work.title}`}
        actions={[
          { id: "open", label: "打开", href: withBasePath(player) },
          { id: "edit", label: "编辑", href: withBasePath(editHref) },
          { id: "share", label: "分享", disabled: working, onSelect: () => { void openShare(work); } },
          { id: "rename", label: "重命名", disabled: unavailable, onSelect: () => startRename(work) },
          { id: "cover", label: "编辑封面", disabled: unavailable,
            onSelect: () => { setDialogError(""); setCover(work); } },
          { id: "publication", label: publicOrRevoking ? "取消发布" : "发布",
            disabled: unavailable, onSelect: () => {
              setDialogError("");
              if (publicOrRevoking) setRevoke(work);
              else setPublish(work);
            } },
          { id: "delete", label: "删除", destructive: true, disabled: unavailable,
            onSelect: () => { setDialogError(""); setRemove(work); } },
        ]}>
        <Link href={player} className="history-cover" aria-label={`打开作品：${work.title}`}>
          {current ? <ImagePreview
            src={withBasePath(`/api/forge/works/${work.id}/cover.png?variant=${work.cover_variant || "preview"}&at=${encodeURIComponent(work.updated_at)}`)}
            alt={`${work.title}预览`} fallback="无封面" loading="lazy" /> : <span>预览待生成</span>}
        </Link>
        <div className="history-row-main">
          <div className="history-title-line">
            <h2><Link className="history-card-link" href={player}>{work.title}</Link></h2>
            <span className="history-status done">已完成</span>
          </div>
          <div className="history-meta"><span>更新 {displayTime(work.updated_at)}</span>
            {current && <span>V{current.version_number}</span>}</div>
          {work.summary ? <p className="history-error">{work.summary}</p> : null}
        </div>
      </CollectionCard>;
    })}
    {rename && <ModalFrame title="重命名作品" busy={working} onClose={() => setRename(null)}>
      <div className="history-rename-overlay"><ModalBody><section className="history-rename-dialog">
        <h2>重命名作品</h2>
        <form onSubmit={event => { event.preventDefault(); void saveRename(); }}>
          <label htmlFor="saved-work-rename">作品名称</label>
          <input id="saved-work-rename" autoFocus maxLength={160} required value={name}
            onChange={event => setName(event.target.value)} disabled={working} />
          {dialogError && <p role="alert">{dialogError}</p>}
          <div className="asset-confirm-actions">
            <Button variant="outline" type="button" onClick={() => setRename(null)}>取消</Button>
            <Button variant="primary" type="submit" disabled={working || !name.trim()}>保存</Button>
          </div>
        </form>
      </section></ModalBody></div>
    </ModalFrame>}
    {cover && <WorkPublishDialog key={`cover:${cover.id}`} mode="cover"
      work={workView(cover)} error={dialogError} busy={working}
      onClose={() => setCover(null)} onSubmit={payload => { void saveCover(payload); }} />}
    {publish && <WorkPublishDialog key={`publish:${publish.id}`} work={workView(publish)}
      error={dialogError} busy={working} onClose={() => setPublish(null)}
      onSubmit={payload => { void submitPublish(payload); }} />}
    {shared && <WorkShareDialog data={shared} onClose={() => setShared(null)} />}
    <ConfirmDialog open={Boolean(sharePrompt)} title="请先发布作品"
      description="作品尚未发布到教师资源广场。发布后才可以生成公开分享链接。是否现在发布？"
      onCancel={() => setSharePrompt(null)}
      onConfirm={() => { setPublish(sharePrompt); setSharePrompt(null); }} />
    <ConfirmDialog open={Boolean(revoke)} title="取消发布"
      description="取消后，教师资源广场及已有分享链接将无法访问；你的私人作品会保留。"
      error={revoke ? dialogError : ""} busy={working}
      onCancel={() => setRevoke(null)} onConfirm={() => { void confirmRevoke(); }} />
    <ConfirmDialog open={Boolean(remove)} title="删除作品"
      description="确定永久删除这件互动作品及其历史版本吗？如果已发布，将先撤回公开分享。此操作无法撤销。"
      error={remove ? dialogError : ""} busy={working}
      onCancel={() => setRemove(null)} onConfirm={() => { void confirmDelete(); }} />
  </>;
}
