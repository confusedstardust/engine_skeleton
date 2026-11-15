import { forgeApi } from "../../lib/api-client";
import { workApi } from "../../lib/work-api";
import type { ServerMessage, ConversationArtifact, ConversationDetail } from "../../lib/conversation-api";
import type { PracticeMessage } from "./practice-types";
import { loadSavedWork } from "./practice-work-service";
import type { WorkPreviewData } from "./work-inspector";

/** Convert persisted public messages and origin IDs, never client-supplied HTML. */
export function messagesFromConversation(detail: ConversationDetail): PracticeMessage[] {
  const byOrigin = new Map(detail.artifacts.filter(a => a.originMessageId)
    .map(a => [a.originMessageId!, a]));
  return detail.messages.map((message: ServerMessage) => {
    const origin = byOrigin.get(message.id);
    return {
      role: message.role,
      content: message.content,
      choices: message.metadata?.choices,
      id: message.id,
      seq: message.seq,
      timeline: message.metadata?.timeline as PracticeMessage["timeline"],
      publicBrief: message.metadata?.publicBrief,
      learningPlan: message.metadata?.learningPlan as PracticeMessage["learningPlan"],
      durationMs: message.metadata?.elapsedMs,
      ...(origin ? { work: { artifactId: origin.artifactId, title: origin.title,
        kind: origin.kind, version: 1 } } : {}),
    };
  });
}

/** Artifact content is downloaded only when a preview was explicitly requested.
 * A saved work version is always owner checked; ephemeral blobs may have expired. */
export async function previewConversationArtifact(artifact: ConversationArtifact): Promise<WorkPreviewData> {
  if (artifact.workId) {
    const { work } = await workApi.get(artifact.workId);
    const matching = work.versions.find(v => v.artifact_id === artifact.artifactId);
    if (!matching) throw new Error("目标产物版本不属于这件已保存作品");
    return loadSavedWork(artifact.workId, matching.id);
  }
  const blob = await forgeApi.blob("/nar-agent/artifacts/" + artifact.artifactId + "/index.html");
  return {
    artifactId: artifact.artifactId, html: await blob.text(),
    title: artifact.title, kind: artifact.kind, version: 1,
    publicationStatus: "draft", isHistorical: false, publicUrl: null,
  };
}
