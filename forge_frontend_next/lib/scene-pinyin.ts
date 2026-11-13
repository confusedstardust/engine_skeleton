import { pinyin } from "pinyin-pro";

type Segment = { start: number; end: number; text: string; attributes: string; readings: string[] };
export type PinyinCharacter = { text: string; reading: string; editable: boolean; attributes: string };
export type PinyinSelection = { original: string; start: number; end: number; characters: PinyinCharacter[] };

function segments(source: string): Segment[] {
  const result: Segment[] = [];
  const pattern = /\[([^\[\]\r\n]*)\]\(([^()\r\n]*)\)/g;
  let cursor = 0;
  for (const match of source.matchAll(pattern)) {
    const start = match.index!;
    if (start > cursor) result.push({ start: cursor, end: start, text: source.slice(cursor, start), attributes: "", readings: [] });
    const body = match[2];
    const enhanced = /(?:^|\s)(?:style|tips|style-alltext|ruby)=/.test(body);
    const ruby = enhanced ? /(?:^|\s)ruby=(.*?)(?=\s+\S+=|$)/.exec(body)?.[1] ?? "" : body;
    const attributes = enhanced ? body.replace(/(?:^|\s)ruby=.*?(?=\s+\S+=|$)/, "").trim() : "";
    result.push({ start, end: start + match[0].length, text: match[1], attributes, readings: ruby.trim().split(/\s+/).filter(Boolean) });
    cursor = start + match[0].length;
  }
  if (cursor < source.length) result.push({ start: cursor, end: source.length, text: source.slice(cursor), attributes: "", readings: [] });
  return result;
}

export function preparePinyinSelection(original: string, start: number, end: number): PinyinSelection {
  if (start < 0 || end > original.length || start >= end) throw new Error("请先选中要注音的文字。");
  if (/[\r\n|]/.test(original.slice(start, end))) throw new Error("请在同一段对白内选择文字。");
  const parts = segments(original);
  for (const part of parts) {
    const marked = original.slice(part.start, part.end).startsWith("[");
    if (marked && start < part.end && end > part.start && (start > part.start || end < part.end)) {
      throw new Error("请完整选中已有标记（包括方括号和括号），再修改或移除注音。");
    }
  }
  const context = parts.map(part => part.text).join("");
  const readings = new Map<number, string>();
  let offset = 0;
  for (const item of pinyin(context, { type: "all" })) {
    if (item.isZh) readings.set(offset, item.pinyin);
    offset += item.origin.length;
  }
  offset = 0;
  const characters: PinyinCharacter[] = [];
  for (const part of parts) {
    const marked = original.slice(part.start, part.end).startsWith("[");
    let localOffset = 0;
    let charIndex = 0;
    for (const char of part.text) {
      const sourceOffset = part.start + localOffset;
      const selected = marked ? start <= part.start && end >= part.end : sourceOffset >= start && sourceOffset + char.length <= end;
      const reading = readings.get(offset + localOffset) ?? "";
      if (selected) characters.push({ text: char, reading: part.readings[charIndex] || reading, editable: !!reading, attributes: part.attributes });
      localOffset += char.length;
      charIndex++;
    }
    offset += part.text.length;
  }
  if (!characters.some(character => character.editable)) throw new Error("选中的内容没有可注音的汉字。");
  if (characters.length > 160) throw new Error("一次最多为 160 个字注音，请分段操作。");
  return { original, start, end, characters };
}

export function renderPinyinSelection(selection: PinyinSelection, readings: string[], remove = false): string {
  return selection.characters.map((character, index) => {
    const reading = remove || !character.editable ? "" : (readings[index] ?? "").trim();
    if (reading && !/^[a-zA-Z\u00c0-\u024f\u0300-\u036f0-5'’ -]+$/u.test(reading)) {
      throw new Error(`“${character.text}”的拼音格式不正确。`);
    }
    if (character.attributes) {
      return `[${character.text}](${character.attributes}${reading ? ` ruby=${reading}` : ""})`;
    }
    return reading ? `[${character.text}](${reading})` : character.text;
  }).join("");
}

export function replacePinyinSelection(current: string, selection: PinyinSelection, replacement: string): string {
  if (current !== selection.original) throw new Error("原文已发生变化，请重新选择文字后添加拼音。");
  return current.slice(0, selection.start) + replacement + current.slice(selection.end);
}
