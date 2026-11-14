import { notFound } from "next/navigation";
import { PracticeShell } from "../../practice-shell";

export default async function ConversationPage({ params }: {
  params: Promise<{ conversationId: string }>;
}) {
  const { conversationId } = await params;
  if (!/^[a-f0-9]{32}$/.test(conversationId)) notFound();
  return <PracticeShell key={conversationId} workspaceScope={"chat:" + conversationId}
    conversationId={conversationId} />;
}
