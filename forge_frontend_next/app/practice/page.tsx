"use client";

import { WorkbenchHeader } from "../../components/workbench-header";
import { ConfirmDialog } from "../../components/ui/modal";
import PracticeChat from "./practice-chat";
import WorkShareDialog from "./work-share-dialog";
import WorkPublishDialog from "./work-publish-dialog";
import WorkInspector from "./work-inspector";
import PracticeNavigation from "./practice-navigation";
import ResizableWorkspace from "./resizable-workspace";
import { usePracticeWorkspace } from "./use-practice-workspace";
import styles from "./practice.module.css";

/** Route composition only. Shared chrome stays in WorkbenchHeader and the root SiteFooter. */
export default function PracticePage() {
  const workspace = usePracticeWorkspace();
  const {
    loggedIn, busy, sessionUserId, selectedWork, publishWork, metadataWork,
    setSelectedArtifactId, setCurrentArtifactId, input, savedWorkCount, beginNewConversation,
    savingArtifactId, setPublishArtifactId, setMetadataArtifactId, metadataBusy, metadataError, setMetadataError,
    setRevokeArtifactId, publicationBusy, publicationError, setPublicationError,
    revokeArtifactId, revokeError, setRevokeError, shareData, setShareData,
    saveWork, viewSavedVersion, saveMetadata, submitPublication, revokePublication, openShare,
  } = workspace;

  return <main className={styles.page}>
    <WorkbenchHeader title="互动学习创作" subtitle="NARAGENT STUDIO"
      account={null} brandHref={null} returnHref="/" />
    <ResizableWorkspace userId={sessionUserId}
      navigation={({ collapsed, onToggle }) => <PracticeNavigation loggedIn={loggedIn} busy={busy}
        refreshKey={savedWorkCount} collapsed={collapsed} onToggle={onToggle}
        onNewConversation={beginNewConversation} />}
      chat={<PracticeChat workspace={workspace} />}
      inspector={selectedWork ? <WorkInspector work={selectedWork}
        onClose={() => setSelectedArtifactId(null)}
        onEdit={id => { setCurrentArtifactId(id); input.current?.focus(); }}
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
    {publishWork && <WorkPublishDialog key={publishWork.artifactId} work={publishWork}
      onClose={() => setPublishArtifactId(null)} busy={publicationBusy} error={publicationError}
      onSubmit={payload => { void submitPublication(payload); }} />}
    <ConfirmDialog open={Boolean(revokeArtifactId)} error={revokeError} title="撤回教师广场发布"
      description="撤回后，已有公开链接也将无法继续访问作品。私有作品与版本记录会保留。"
      busy={publicationBusy} onCancel={() => setRevokeArtifactId(null)}
      onConfirm={() => { void revokePublication(); }} />
  </main>;
}
