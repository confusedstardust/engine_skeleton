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


/** Hide half-received control markers without hiding ordinary Markdown. */
export function visibleAgentChoicePrefix(text: string): string {
  const start = text.indexOf(START);
  if (start >= 0) return text.slice(0, start).trimEnd();
  for (let i = Math.min(START.length - 1, text.length); i > 0; i--) {
    if (text.slice(-i).toLowerCase() === START.slice(0, i).toLowerCase()) return text.slice(0, -i);
  }
  return text;
}

export function parseAgentChoiceMessage(content: string): {
  body: string;
  choice: AgentChoiceQuestion | null;
} {
  const start = content.lastIndexOf(START);
  if (start < 0) return { body: visibleAgentChoicePrefix(content), choice: null };
  const body = content.slice(0, start).trimEnd();
  const stop = content.indexOf(END, start + START.length);
  // Always hide protocol-like output even if the model fails to close JSON,
  // exceeds length limits, or appends explanatory text after the marker.
  if (stop < 0 || content.slice(stop + END.length).trim())
    return { body: body || "请说明你希望下一步怎么做。", choice: null };

  const raw = content.slice(start + START.length, stop).trim();
  if (raw.length > 7000) return { body, choice: null };
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { body, choice: null };
    }
    const data = parsed as Record<string, unknown>;
    if (typeof data.question !== "string" || !data.question.trim()
      || data.question.length > 300 || !Array.isArray(data.options)
      || data.options.length < 2 || data.options.length > 6
      || typeof data.multiple !== "boolean"
      || typeof data.allowCustom !== "boolean") {
      return { body, choice: null };
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
        || !o.label.trim() || o.label.length > 240
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
      body,
      choice: {
        question: data.question.trim(),
        options,
        multiple: data.multiple,
        allowCustom: data.allowCustom,
      },
    };
  } catch {
    return { body, choice: null };
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
