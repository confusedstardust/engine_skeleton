/**
 * V1 conversation-level selection protocol.
 * The canonical assistant message remains plain text in the existing ledger.
 * A valid trailing marker is progressively enhanced into clickable options;
 * previous messages and clients retain ordinary text fallback.
 *
 * Never parse arbitrary numbered lists into executable actions.
 */
export type AgentChoiceQuestion = {
  question: string;
  options: { id: string; label: string; description?: string }[];
  multiple: boolean;
  allowCustom: boolean;
};

const START = "[[NAR_UI_CHOICES_V1]]";
const END = "[[/NAR_UI_CHOICES_V1]]";

export function parseAgentChoiceMessage(content: string): {
  body: string;
  choice: AgentChoiceQuestion | null;
} {
  const start = content.lastIndexOf(START);
  if (start < 0) return { body: content, choice: null };
  const stop = content.indexOf(END, start + START.length);
  if (stop < 0 || content.slice(stop + END.length).trim()) return { body: content, choice: null };

  const raw = content.slice(start + START.length, stop).trim();
  if (raw.length > 3000) return { body: content, choice: null };
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { body: content, choice: null };
    }
    const data = parsed as Record<string, unknown>;
    if (typeof data.question !== "string" || !data.question.trim()
      || data.question.length > 300 || !Array.isArray(data.options)
      || data.options.length < 2 || data.options.length > 5
      || typeof data.multiple !== "boolean"
      || typeof data.allowCustom !== "boolean") {
      return { body: content, choice: null };
    }
    const ids = new Set<string>();
    const options: AgentChoiceQuestion["options"] = [];
    for (const item of data.options) {
      if (!item || typeof item !== "object" || Array.isArray(item)) {
        return { body: content, choice: null };
      }
      const o = item as Record<string, unknown>;
      if (typeof o.id !== "string" || !/^[a-zA-Z0-9_-]{1,16}$/.test(o.id)
        || ids.has(o.id) || typeof o.label !== "string"
        || !o.label.trim() || o.label.length > 100
        || (o.description !== undefined && (typeof o.description !== "string"
          || o.description.length > 240))) {
        return { body: content, choice: null };
      }
      ids.add(o.id);
      options.push({
        id: o.id,
        label: o.label.trim(),
        ...(typeof o.description === "string" ? { description: o.description.trim() } : {}),
      });
    }
    return {
      body: content.slice(0, start).trimEnd(),
      choice: {
        question: data.question.trim(),
        options,
        multiple: data.multiple,
        allowCustom: data.allowCustom,
      },
    };
  } catch {
    return { body: content, choice: null };
  }
}

/** Include the actual selected label, never rely on bare "A" or "1" context. */
export function formatAgentChoiceAnswer(
  choice: AgentChoiceQuestion,
  selectedIds: string[],
  custom = "",
): string {
  const selected = choice.options.filter(o => selectedIds.includes(o.id)).map(o => o.label);
  const extra = choice.allowCustom ? custom.trim() : "";
  return [
    selected.length ? "我选择：" + selected.join("、") : "",
    extra ? "补充要求：" + extra : "",
  ].filter(Boolean).join("\n");
}
