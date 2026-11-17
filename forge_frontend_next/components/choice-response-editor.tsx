"use client";

import type { SceneChoice, SceneLine } from "../domain/narrative";
import { randomUUID } from "../app/random-uuid";
import { Button } from "./ui/button";
import { FormSelect } from "./ui/form-controls";
import { ScenePinyinTextarea } from "./scene-pinyin-textarea";
import { useRef } from "react";
import { useSceneLineDrag } from "../hooks/use-scene-line-drag";

export function ChoiceResponseEditor({ choice, speakers, disabled, onChange }: {
  choice: SceneChoice;
  speakers: string[];
  disabled: boolean;
  onChange: (choice: SceneChoice) => void;
}) {
  const lines = choice.response_lines || [];
  const containerRef = useRef<HTMLDetailsElement>(null);
  const { dragIndex, dropHint, startLineDrag, moveLineDrag, finishLineDrag } = useSceneLineDrag({
    disabled, containerRef, selector: "[data-response-index]", indexAttribute: "data-response-index", onReorder: move,
  });
  function update(next: SceneLine[]) {
    onChange({ ...choice, id: choice.id || randomUUID(), response_lines: next });
  }
  function add(narration: boolean) {
    const speaker = narration ? "旁白" : speakers.find(name => name !== "旁白") || "角色";
    update([...lines, { id: randomUUID(), kind: narration ? "narration" : "dialogue", speaker, text: "", rawPrefix: narration ? "旁白" : "" }]);
  }
  function move(from: number, to: number) {
    if (disabled || from < 0 || to < 0 || from === to) return;
    const next = [...lines];
    const [line] = next.splice(from, 1);
    next.splice(to, 0, line);
    update(next);
  }
  return (
    <details className="laper-choice-responses" ref={containerRef}>
      <summary>专属对话</summary>
      {lines.map((line, index) => (
        <div className={`laper-response-line ${dragIndex === index ? "dragging" : ""} ${dragIndex !== index && dropHint?.index === index ? `drop-${dropHint.placement}` : ""}`} key={line.id} data-response-line={line.id} data-response-index={index}>
          {!disabled && <Button variant="unstyled" className="laper-drag-handle" aria-label="拖动专属对话排序"
            onPointerDown={event => { if (event.button !== 0) return; event.preventDefault(); event.stopPropagation(); event.currentTarget.setPointerCapture(event.pointerId); startLineDrag(index, event.pointerId, event.clientY); }}
            onPointerMove={event => moveLineDrag(event.pointerId, event.clientX, event.clientY)}
            onPointerUp={event => { finishLineDrag(event.pointerId); event.currentTarget.releasePointerCapture(event.pointerId); }}
            onPointerCancel={event => finishLineDrag(event.pointerId)}>⋮⋮</Button>}
          <div className="laper-block-content">
          <div className="laper-block-head">
          <FormSelect classes={{ trigger: "laper-speaker laper-response-speaker" }} value={line.speaker} ariaLabel={`第 ${index + 1} 句说话人`} disabled={disabled} options={Array.from(new Set([...speakers, line.speaker])).map(name => ({ value: name, label: name }))} onValueChange={speaker => update(lines.map((item, i) => i === index ? { ...item, speaker, kind: speaker === "旁白" ? "narration" : "dialogue", rawPrefix: speaker === "旁白" ? "旁白" : "" } : item))} />
          <em>{line.kind === "narration" ? "旁白" : "对话"}</em>
          {!disabled && <div className="laper-response-actions">
            <Button variant="unstyled" className="laper-block-delete" type="button" onClick={() => update(lines.filter((_, i) => i !== index))}>删除</Button>
          </div>}
          </div>
          <ScenePinyinTextarea className="laper-block-body" rows={2} value={line.text} onValueChange={text => update(lines.map((item, i) => i === index ? { ...item, text } : item))} aria-label={`第 ${index + 1} 句专属对话`} readOnly={disabled} />
          </div>
        </div>
      ))}
      {!disabled && <div className="laper-response-footer"><Button variant="unstyled" className="laper-block-add" type="button" onClick={() => add(false)}>＋ 对白</Button><Button variant="unstyled" className="laper-block-add" type="button" onClick={() => add(true)}>＋ 旁白</Button></div>}
    </details>
  );
}
