"use client";

import { WorkbenchHeader } from "../../components/workbench-header";
import SiteFooter from "../../components/site-footer";
import { ConfirmDialog } from "../../components/ui/modal";
import PracticeChat from "./practice-chat";
import WorkShareDialog from "./work-share-dialog";
import WorkPublishDialog from "./work-publish-dialog";
import WorkInspector from "./work-inspector";
import PracticeNavigation from "./practice-navigation";
import ResizableWorkspace from "./resizable-workspace";
import { usePracticeWorkspace } from "./use-practice-workspace";
import styles from "./practice.module.css";

/** The studio aligns the shared bars to its resizable sidebar. */
export function PracticeShell({ workspaceScope, conversationId }: { workspaceScope: string; conversationId?: string }) {
  const workspace = usePracticeWorkspace(workspaceScope, conversationId);
  const {
    loggedIn, busy, sessionUserId, selectedWork, publishWork, metadataWork,
    serverReady, serverChecked,
    setSelectedArtifactId, beginNewConversation,
    savingArtifactId, setPublishArtifactId, setMetadataArtifactId, metadataBusy, metadataError, setMetadataError,
    setRevokeArtifactId, publicationBusy, publicationError, setPublicationError,
    revokeArtifactId, revokeError, setRevokeError, shareData, setShareData,
    shareNoticeArtifactId, setShareNoticeArtifactId,
    saveWork, viewSavedVersion, saveMetadata, submitPublication, revokePublication, openShare,
  } = workspace;

  return <main className={styles.page}>
    <ResizableWorkspace userId={sessionUserId}
      header={<WorkbenchHeader title="互动学习创作" subtitle="NARAGENT STUDIO" />}
      footer={<SiteFooter />}
      navigation={({ collapsed, onToggle }) => <PracticeNavigation loggedIn={loggedIn} busy={busy}
        serverReady={serverReady} serverChecked={serverChecked} ownerId={sessionUserId} activeConversationId={conversationId ?? null} collapsed={collapsed} onToggle={onToggle}
        onNewConversation={beginNewConversation} />}
      chat={<PracticeChat workspace={workspace} />}
      inspector={selectedWork ? <WorkInspector work={selectedWork}
        onClose={() => setSelectedArtifactId(null)}
        onSave={id => { void saveWork(id); }} saving={savingArtifactId === selectedWork.artifactId}
        onEditMetadata={id => { setMetadataError(""); setMetadataArtifactId(id); }}
        onViewVersion={(workId, versionId) => { void viewSavedVersion(workId, versionId); }}
        onPublish={id => { setPublicationError(""); setPublishArtifactId(id); }}
        onUnpublish={id => { setRevokeError(""); setRevokeArtifactId(id); }}
        onShare={id => { void openShare(id); }}
        publishing={publicationBusy} /> : undefined} />
    {metadataWork && <WorkPublishDialog key={"metadata:" + metadataWork.artifactId}
      mode="edit" work={metadataWork} onClose={() => setMetadataArtifactId(null)}
      busy={metadataBusy} error={metadataError}
      onSubmit={payload => { void saveMetadata(payload); }} />}
    {shareData && <WorkShareDialog data={shareData} onClose={() => setShareData(null)} />}
    <ConfirmDialog open={Boolean(shareNoticeArtifactId)} title="请先发布作品"
      description="作品尚未发布到教师资源广场。发布后即可生成公开链接和分享海报。是否现在去发布？"
      onCancel={() => setShareNoticeArtifactId(null)}
      onConfirm={() => {
        if (shareNoticeArtifactId) setPublishArtifactId(shareNoticeArtifactId);
        setShareNoticeArtifactId(null);
      }} />
    {publishWork && <WorkPublishDialog key={publishWork.artifactId} work={publishWork}
      onClose={() => setPublishArtifactId(null)} busy={publicationBusy} error={publicationError}
      onSubmit={payload => { void submitPublication(payload); }} />}
    <ConfirmDialog open={Boolean(revokeArtifactId)} error={revokeError} title="撤回教师广场发布"
      description="撤回后，已有公开链接也将无法继续访问作品。私有作品与版本记录会保留。"
      busy={publicationBusy} onCancel={() => setRevokeArtifactId(null)}
      onConfirm={() => { void revokePublication(); }} />
  </main>;
}

