"use client";

import type { ReactNode } from "react";
import styles from "./practice.module.css";

/**
 * Render the small Markdown subset needed for NarAgent explanations.
 * No HTML parser, raw HTML injection, embedded images, or dynamic script support:
 * every model-supplied character is rendered as ordinary escaped React text.
 */
function inline(text: string): ReactNode[] {
  const tokens: ReactNode[] = [];
  const pattern = /\*\*([^*\n]+)\*\*|`([^`\n]+)`|\[([^\]\n]+)\]\(([^\s)]+)\)|\*([^*\n]+)\*/g;
  let at = 0;
  for (const match of text.matchAll(pattern)) {
    const i = match.index;
    if (i > at) tokens.push(text.slice(at, i));
    const key = `inline-${i}`;
    if (match[1]) tokens.push(<strong key={key}>{match[1]}</strong>);
    else if (match[2]) tokens.push(<code key={key}>{match[2]}</code>);
    else if (match[3]) {
      let safe = false;
      try { safe = ["https:", "http:"].includes(new URL(match[4]).protocol); }
      catch { /* Other schemes and relative URLs remain plain text. */ }
      tokens.push(safe
        ? <a key={key} href={match[4]} target="_blank" rel="noopener noreferrer nofollow">{match[3]}</a>
        : match[0]);
    } else if (match[5]) tokens.push(<em key={key}>{match[5]}</em>);
    at = i + match[0].length;
  }
  if (at < text.length) tokens.push(text.slice(at));
  return tokens.length ? tokens : [text];
}

function isSeparator(line: string) {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
}
function cells(line: string) {
  return line.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map(cell => cell.trim());
}
function blockStart(line: string) {
  return /^\s*(?:#{1,3}\s|[-*+]\s|\d+\.\s|>\s?|\`\`\`)/.test(line);
}

export default function MessageMarkdown({ content }: { content: string }) {
  const lines = content.replace(/\r\n?/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    if (!lines[i].trim()) { i++; continue; }
    const key = `block-${i}`;
    const start = lines[i];
    if (/^\s*\`\`\`/.test(start)) {
      const language = start.trim().slice(3).trim().slice(0, 20);
      const code: string[] = [];
      i++;
      while (i < lines.length && !/^\s*\`\`\`/.test(lines[i])) code.push(lines[i++]);
      if (i < lines.length) i++;
      blocks.push(<pre key={key} data-language={language}><code>{code.join("\n")}</code></pre>);
      continue;
    }
    const heading = start.match(/^\s*(#{1,3})\s+(.+)$/);
    if (heading) {
      const text = inline(heading[2].trim());
      blocks.push(heading[1].length === 1 ? <h3 key={key}>{text}</h3> :
        heading[1].length === 2 ? <h4 key={key}>{text}</h4> : <h5 key={key}>{text}</h5>);
      i++;
      continue;
    }
    if (i + 1 < lines.length && lines[i].includes("|") && isSeparator(lines[i + 1])) {
      const heads = cells(lines[i]);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) rows.push(cells(lines[i++]));
      blocks.push(<div key={key} className={styles.markdownTableWrap}><table><thead><tr>{heads.map((cell, index) => <th key={index}>{inline(cell)}</th>)}</tr></thead><tbody>{rows.map((row, rowIndex) => <tr key={rowIndex}>{heads.map((_, index) => <td key={index}>{inline(row[index] || "")}</td>)}</tr>)}</tbody></table></div>);
      continue;
    }
    if (/^\s*>\s?/.test(start)) {
      const parts: string[] = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) parts.push(lines[i++].replace(/^\s*>\s?/, ""));
      blocks.push(<blockquote key={key}>{parts.map((line, index) => <p key={index}>{inline(line)}</p>)}</blockquote>);
      continue;
    }
    const listMatch = start.match(/^\s*([-*+]|\d+\.)\s+(.+)$/);
    if (listMatch) {
      const ordered = /^\d/.test(listMatch[1]);
      const items: string[] = [];
      while (i < lines.length) {
        const found = lines[i].match(/^\s*([-*+]|\d+\.)\s+(.+)$/);
        if (!found || /^\d/.test(found[1]) !== ordered) break;
        items.push(found[2]); i++;
      }
      const children = items.map((item, index) => <li key={index}>{inline(item)}</li>);
      blocks.push(ordered ? <ol key={key}>{children}</ol> : <ul key={key}>{children}</ul>);
      continue;
    }
    const paragraph = [start.trim()];
    i++;
    while (i < lines.length && lines[i].trim() && !blockStart(lines[i]) &&
      !(i + 1 < lines.length && lines[i].includes("|") && isSeparator(lines[i + 1]))) {
      paragraph.push(lines[i].trim()); i++;
    }
    blocks.push(<p key={key}>{paragraph.map((part, index) =>
      <span key={index}>{index ? <br /> : null}{inline(part)}</span>)}</p>);
  }
  return <div className={styles.markdown}>{blocks}</div>;
}
