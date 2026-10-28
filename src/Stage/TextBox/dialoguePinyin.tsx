import { cloneElement, isValidElement, ReactNode } from 'react';
import { pinyin } from 'pinyin-pro';
import type { EnhancedNode } from './TextBox';

export function addDialoguePinyin(lines: EnhancedNode[][]): EnhancedNode[][] {
  return lines.map(line => {
    const text = line.map(node => node.plainText ?? '').join('');
    const readings = new Map<number, string>();
    let offset = 0;
    for (const item of pinyin(text, { type: 'all' })) {
      if (item.isZh && item.pinyin) readings.set(offset, item.pinyin);
      offset += item.origin.length;
    }
    offset = 0;
    return line.map(node => {
      const start = offset;
      const value = node.plainText ?? '';
      offset += value.length;
      if (node.manualRuby || !value) return node;
      let cursor = start;
      let annotated = false;
      const children: ReactNode[] = Array.from(value, (char, index) => {
        const reading = readings.get(cursor);
        cursor += char.length;
        if (!reading) return char;
        annotated = true;
        return <ruby className="dialogue-pinyin-ruby" key={index}>{char}<rt>{reading}</rt></ruby>;
      });
      if (!annotated) return node;
      const reactNode = isValidElement(node.reactNode)
        ? cloneElement(node.reactNode, undefined, ...children)
        : <>{children}</>;
      return { ...node, reactNode };
    });
  });
}
