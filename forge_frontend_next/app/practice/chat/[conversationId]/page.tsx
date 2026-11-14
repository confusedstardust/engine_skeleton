import { notFound } from "next/navigation";

/** Route validation only; the persistent practice layout owns the studio. */
export default async function ConversationPage({ params }: {
  params: Promise<{ conversationId: string }>;
}) {
  const { conversationId } = await params;
  if (!/^[a-f0-9]{32}$/.test(conversationId)) notFound();
  return null;
}
