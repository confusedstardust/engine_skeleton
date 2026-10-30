"use client";
import { InlineFeedback } from './ui/feedback';
import { DialogHeader } from './ui/dialog-header';
import { DialogActions } from './ui/dialog-actions';

import { Button } from './ui/button';

import { useRef, useState, type ComponentProps } from "react";
import * as Dialog from "./ui/dialog";
import { preparePinyinSelection, renderPinyinSelection, replacePinyinSelection, type PinyinSelection } from "../lib/scene-pinyin";
import styles from "./scene-pinyin-textarea.module.css";

type Props = Omit<ComponentProps<"textarea">, "value" | "onChange"> & {
  value: string;
  onValueChange: (value: string) => void;
};

export function ScenePinyinTextarea({ value, onValueChange, readOnly, disabled, ...props }: Props) {
  const input = useRef<HTMLTextAreaElement>(null);
  const current = useRef(value);
  current.current = value;
  const [range, setRange] = useState<{ original: string; start: number; end: number } | null>(null);
  const [selection, setSelection] = useState<PinyinSelection | null>(null);
  const [readings, setReadings] = useState<string[]>([]);
  const [error, setError] = useState("");
  const history = useRef<{ before: string; after: string; start: number; end: number; undone: boolean } | null>(null);
  const pendingFocus = useRef<{ start: number; end: number } | null>(null);
  const locked = !!readOnly || !!disabled;

  function capture() {
    const field = input.current;
    if (!field || locked || field.selectionStart === field.selectionEnd) { setRange(null); return; }
    setError("");
    setRange({ original: field.value, start: field.selectionStart, end: field.selectionEnd });
  }

  function open() {
    if (!range || locked) return;
    try {
      if (range.original !== current.current) throw new Error("原文已发生变化，请重新选择文字。");
      const prepared = preparePinyinSelection(range.original, range.start, range.end);
      pendingFocus.current = { start: range.start, end: range.end };
      setSelection(prepared); setReadings(prepared.characters.map(character => character.reading)); setError("");
    } catch (cause) { setError((cause as Error).message); }
  }

  function apply(remove = false) {
    if (!selection || locked) return;
    try {
      const replacement = renderPinyinSelection(selection, readings, remove);
      const next = replacePinyinSelection(current.current, selection, replacement);
      history.current = { before: current.current, after: next, start: selection.start, end: selection.end, undone: false };
      pendingFocus.current = { start: selection.start, end: selection.start + replacement.length };
      onValueChange(next); setSelection(null); setRange(null); setError("");
    } catch (cause) { setError((cause as Error).message); }
  }

  return <div className={styles.wrapper}>
    <textarea {...props} ref={input} value={value} readOnly={readOnly} disabled={disabled}
      onChange={event => { history.current = null; setRange(null); onValueChange(event.target.value); }}
      onMouseUp={capture} onKeyUp={capture} onSelect={capture}
      onBlur={event => { if (!event.relatedTarget || !(event.relatedTarget instanceof Element) || !event.relatedTarget.closest('[data-pinyin-menu]')) setRange(null); }}
      onKeyDown={event => {
        props.onKeyDown?.(event);
        if (locked || event.defaultPrevented) return;
        if (event.key === "Escape") { setRange(null); return; }
        const entry = history.current;
        if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "z" || !entry) return;
        if (!event.shiftKey && !entry.undone && current.current === entry.after) {
          event.preventDefault(); entry.undone = true; onValueChange(entry.before); setRange(null);
        } else if (event.shiftKey && entry.undone && current.current === entry.before) {
          event.preventDefault(); entry.undone = false; onValueChange(entry.after); setRange(null);
        }
      }} />
    {range && !locked && !selection && <div className={styles.menu} data-pinyin-menu role="toolbar" aria-label="选中文字操作"
      onMouseDown={event => event.preventDefault()}>
      <Button variant="unstyled" type="button" onClick={open}>添加 / 修改拼音</Button>
    </div>}
    {error && !selection && <InlineFeedback className={styles.error} >{error}</InlineFeedback>}
    <Dialog.Root open={!!selection && !locked} onOpenChange={open => { if (!open) { setSelection(null); setError(""); } }}>
      <Dialog.Surface className={styles.dialog} aria-describedby="scene-pinyin-description"
        onCloseAutoFocus={event => {
          event.preventDefault();
          const target = pendingFocus.current ?? (selection ? { start: selection.start, end: selection.end } : null);
          requestAnimationFrame(() => {
            input.current?.focus({ preventScroll: true });
            if (target) input.current?.setSelectionRange(target.start, target.end);
            pendingFocus.current = null;
          });
        }}>
        <DialogHeader dialogTitle className={styles.header} title="为选中文字添加拼音" subtitle={<Dialog.Description id="scene-pinyin-description">校正多音字后插入。留空可让对应汉字不显示拼音。</Dialog.Description>} closeLabel="关闭拼音编辑" onClose={() => { setSelection(null); setError(''); }} />
        <div className={styles.preview} aria-label="注音预览">{selection?.characters.map((character, index) => readings[index]?.trim() && character.editable
          ? <ruby key={index}>{character.text}<rt>{readings[index]}</rt></ruby> : <span key={index}>{character.text}</span>)}</div>
        <div className={styles.grid}>{selection?.characters.map((character, index) => character.editable && <label key={index}>
          <span>{character.text}</span><input aria-label={`第${index + 1}字“${character.text}”的拼音`} value={readings[index] ?? ""} autoComplete="off" spellCheck={false}
            onChange={event => setReadings(values => values.map((reading, position) => position === index ? event.target.value : reading))} />
        </label>)}</div>
        {error && <InlineFeedback className={styles.error} >{error}</InlineFeedback>}
        <DialogActions as="footer" className={styles.footer}>
          <Button variant="ghost" type="button" onClick={() => apply(true)}>移除所选注音</Button>
          <div><Dialog.Close asChild><Button variant="outline" type="button">取消</Button></Dialog.Close>
            <Button variant="primary" type="button" onClick={() => apply()}>插入拼音</Button></div>
        </DialogActions>
      </Dialog.Surface>
    </Dialog.Root>
  </div>;
}
