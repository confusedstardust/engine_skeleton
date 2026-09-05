"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { LaperInspectorShell } from "./laper-inspector-shell";

export type StoryStep = {
  id: string;
  name: string;
  content: string;
  narrative_target: string;
  strtype: string;
};

export type NarrativeCharacter = {
  id: string;
  name: string;
  gender: string;
  personality: string;
  motivation: string;
  speech_style: string;
  emotional_arc: string;
  relationships: { with: string; dynamic: string }[];
};

export type NarrativeEnding = {
  ending_type: string;
  description: string;
};

export type NarrativePlan = {
  title: string;
  theme: string;
  emotion_tone: string;
  conflict_structure: string;
  story_progression: StoryStep[];
  story_arc: string;
  characters: NarrativeCharacter[];
  touchable_points: string[];
  must_avoid: string[];
  endings: NarrativeEnding[];
  beat_structure: string[];
  narrative_structure: string;
};

type OutlineSection = "phases" | "endings" | "characters";

type SyncOptions = {
  quiet?: boolean;
  force?: boolean;
};

type LaperOutlineWorkbenchProps = {
  plan: NarrativePlan;
  busy: boolean;
  planDirty: boolean;
  flowSyncing: boolean;
  locked: boolean;
  autoMode: boolean;
  phaseBrief: string;
  endingBrief: string;
  characterBrief: string;
  pendingPhaseBrief: string;
  pendingEndingBrief: string;
  pendingCharacterBrief: string;
  setPhaseBrief: (value: string) => void;
  setEndingBrief: (value: string) => void;
  setCharacterBrief: (value: string) => void;
  updatePlan: (plan: NarrativePlan) => void;
  addPhase: () => void;
  addEnding: () => void;
  addCharacter: () => void;
  savePlan: () => void;
  syncStructure: (targetPlan?: NarrativePlan | null, options?: SyncOptions) => Promise<void>;
  nextToScenes: () => void;
  retryAction?: () => void;
  retryLabel?: string;
  renderFlowModal: (open: boolean, onClose: () => void) => React.ReactNode;
};

const SECTIONS: { id: OutlineSection; label: string; hint: string }[] = [
  { id: "characters", label: "角色阵容", hint: "可增删角色，并补充性格与动机。" },
  { id: "phases", label: "故事阶段", hint: "拖动左侧把手可调整顺序，直接点击文本即可修改。" },
  { id: "endings", label: "结局节点", hint: "每个结局会在下一步生成独立场景。" }
];

function reorder<T>(items: T[], from: number, to: number) {
  if (from === to || from < 0 || to < 0 || from >= items.length || to >= items.length) return items;
  const next = [...items];
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved);
  return next;
}

function nextPhaseId(plan: NarrativePlan) {
  const used = new Set(plan.story_progression.map((step) => step.id));
  let index = plan.story_progression.length;
  while (used.has(`phase${index}`)) index += 1;
  return `phase${index}`;
}

function nextCharacterId(plan: NarrativePlan) {
  const used = new Set(plan.characters.map((character) => character.id));
  let index = plan.characters.length;
  while (used.has(`character_${index}`)) index += 1;
  return `character_${index}`;
}

function blockLabel(section: OutlineSection, plan: NarrativePlan, index: number) {
  if (section === "phases") return plan.story_progression[index]?.name || `阶段 ${index + 1}`;
  if (section === "endings") return plan.endings[index]?.ending_type || `结局 ${index + 1}`;
  return plan.characters[index]?.name || plan.characters[index]?.id || `角色 ${index + 1}`;
}

export function LaperOutlineWorkbench(props: LaperOutlineWorkbenchProps) {
  const [section, setSection] = useState<OutlineSection>("characters");
  const [expandedSection, setExpandedSection] = useState<OutlineSection | null>("characters");
  const [activeIndex, setActiveIndex] = useState(0);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [dropHint, setDropHint] = useState<{ index: number; placement: "before" | "after" } | null>(null);
  const [showFlowModal, setShowFlowModal] = useState(false);
  const dragPointerYRef = useRef<number | null>(null);
  const autoScrollFrameRef = useRef<number | null>(null);
  const pointerDragIdRef = useRef<number | null>(null);
  const dragIndexRef = useRef<number | null>(null);
  const dropHintRef = useRef<{ index: number; placement: "before" | "after" } | null>(null);
  const latestPlanRef = useRef(props.plan);
  const disabled = props.locked || props.busy;

  const sectionCount = useMemo(() => {
    if (section === "phases") return props.plan.story_progression.length;
    if (section === "endings") return props.plan.endings.length;
    return props.plan.characters.length;
  }, [props.plan, section]);

  const briefValue = section === "phases" ? props.phaseBrief : section === "endings" ? props.endingBrief : props.characterBrief;
  const setBriefValue =
    section === "phases" ? props.setPhaseBrief : section === "endings" ? props.setEndingBrief : props.setCharacterBrief;
  const pendingBrief =
    section === "phases" ? props.pendingPhaseBrief : section === "endings" ? props.pendingEndingBrief : props.pendingCharacterBrief;
  const addWithAi = section === "phases" ? props.addPhase : section === "endings" ? props.addEnding : props.addCharacter;

  function stopDragAutoScroll() {
    dragPointerYRef.current = null;
    pointerDragIdRef.current = null;
    dragIndexRef.current = null;
    dropHintRef.current = null;
    setDropHint(null);
    if (autoScrollFrameRef.current !== null) {
      window.cancelAnimationFrame(autoScrollFrameRef.current);
      autoScrollFrameRef.current = null;
    }
  }

  function updateDragAutoScroll(pointerY: number) {
    dragPointerYRef.current = pointerY;
    if (autoScrollFrameRef.current !== null) return;

    const scroll = () => {
      const currentY = dragPointerYRef.current;
      if (currentY === null) {
        autoScrollFrameRef.current = null;
        return;
      }
      // Drag events only fire while hovering a droppable element. Keep the
      // window listener below as the authoritative pointer feed so a card can
      // be carried through the page header/footer without losing autoscroll.
      const viewportTop = window.visualViewport?.offsetTop || 0;
      const viewportHeight = window.visualViewport?.height || window.innerHeight;
      // This mirrors document editors: a fixed edge lane with accelerating
      // speed. Pointer capture (below), rather than a giant hit area, is what
      // keeps it reliable while crossing cards or the browser edge.
      const topEdge = Math.min(179, Math.round(viewportHeight * 0.192));
      const bottomEdge = topEdge;
      const distanceFromTop = currentY - viewportTop;
      const distanceFromBottom = viewportTop + viewportHeight - currentY;
      let delta = 0;
      if (distanceFromTop < topEdge) {
        delta = -Math.max(6, Math.round(((topEdge - distanceFromTop) / topEdge) * 27));
      } else if (distanceFromBottom < bottomEdge) {
        delta = Math.max(6, Math.round(((bottomEdge - distanceFromBottom) / bottomEdge) * 27));
      }
      if (!delta) {
        autoScrollFrameRef.current = null;
        return;
      }
      window.scrollBy({ top: delta, behavior: "auto" });
      autoScrollFrameRef.current = window.requestAnimationFrame(scroll);
    };
    autoScrollFrameRef.current = window.requestAnimationFrame(scroll);
  }

  useEffect(() => () => stopDragAutoScroll(), []);

  useEffect(() => {
    latestPlanRef.current = props.plan;
  }, [props.plan]);

  function startPointerDrag(index: number, pointerId: number, pointerY: number) {
    if (disabled) return;
    pointerDragIdRef.current = pointerId;
    dragIndexRef.current = index;
    dropHintRef.current = null;
    setDropHint(null);
    setDragIndex(index);
    updateDragAutoScroll(pointerY);
  }

  function movePointerDrag(pointerId: number, pointerX: number, pointerY: number) {
    if (pointerDragIdRef.current !== pointerId) return;
    updateDragAutoScroll(pointerY);
    const card = document.elementFromPoint(pointerX, pointerY)?.closest<HTMLElement>("[data-laper-outline-index]");
    const targetIndex = Number(card?.dataset.laperOutlineIndex);
    const sourceIndex = dragIndexRef.current;
    if (sourceIndex === null || Number.isNaN(targetIndex) || targetIndex === sourceIndex) {
      if (dropHintRef.current !== null) {
        dropHintRef.current = null;
        setDropHint(null);
      }
      return;
    }
    const bounds = card?.getBoundingClientRect();
    const placement = bounds && pointerY > bounds.top + bounds.height / 2 ? "after" : "before";
    const nextHint = { index: targetIndex, placement } as const;
    if (dropHintRef.current?.index !== nextHint.index || dropHintRef.current.placement !== nextHint.placement) {
      dropHintRef.current = nextHint;
      setDropHint(nextHint);
    }
  }

  function finishPointerDrag(pointerId: number) {
    if (pointerDragIdRef.current !== pointerId) return;
    const sourceIndex = dragIndexRef.current;
    const target = dropHintRef.current;
    if (sourceIndex !== null && target && sourceIndex !== target.index) {
      let insertionIndex = target.index + (target.placement === "after" ? 1 : 0);
      // reorder() removes the source first, so every destination after it
      // shifts left by one before insertion.
      if (sourceIndex < insertionIndex) insertionIndex -= 1;
      reorderSection(sourceIndex, insertionIndex);
    }
    setDragIndex(null);
    stopDragAutoScroll();
  }

  function addBlankBlock() {
    if (disabled) return;
    if (section === "phases") {
      const step: StoryStep = {
        id: nextPhaseId(props.plan),
        name: "",
        content: "",
        narrative_target: "",
        strtype: "main"
      };
      props.updatePlan({ ...props.plan, story_progression: [...props.plan.story_progression, step] });
      setActiveIndex(props.plan.story_progression.length);
      return;
    }
    if (section === "endings") {
      props.updatePlan({
        ...props.plan,
        endings: [...props.plan.endings, { ending_type: "", description: "" }]
      });
      setActiveIndex(props.plan.endings.length);
      return;
    }
    props.updatePlan({
      ...props.plan,
      characters: [
        ...props.plan.characters,
        {
          id: nextCharacterId(props.plan),
          name: "",
          gender: "",
          personality: "",
          motivation: "",
          speech_style: "",
          emotional_arc: "",
          relationships: []
        }
      ]
    });
    setActiveIndex(props.plan.characters.length);
  }

  function reorderSection(from: number, to: number) {
    if (disabled) return;
    const currentPlan = latestPlanRef.current;
    if (section === "phases") {
      latestPlanRef.current = { ...currentPlan, story_progression: reorder(currentPlan.story_progression, from, to) };
    } else if (section === "endings") {
      latestPlanRef.current = { ...currentPlan, endings: reorder(currentPlan.endings, from, to) };
    } else {
      latestPlanRef.current = { ...currentPlan, characters: reorder(currentPlan.characters, from, to) };
    }
    props.updatePlan(latestPlanRef.current);
    setActiveIndex(to);
  }

  function removeAt(index: number) {
    if (disabled) return;
    if (section === "phases") {
      props.updatePlan({
        ...props.plan,
        story_progression: props.plan.story_progression.filter((_, itemIndex) => itemIndex !== index)
      });
    } else if (section === "endings") {
      props.updatePlan({ ...props.plan, endings: props.plan.endings.filter((_, itemIndex) => itemIndex !== index) });
    } else {
      props.updatePlan({ ...props.plan, characters: props.plan.characters.filter((_, itemIndex) => itemIndex !== index) });
    }
    setActiveIndex(Math.max(0, index - 1));
  }

  function openFlowPreview() {
    if (props.planDirty && !disabled) {
      void props.syncStructure(props.plan, { quiet: true });
    }
    setShowFlowModal(true);
  }

  const sectionMeta = SECTIONS.find((item) => item.id === section)!;

  return (
    <section className={`laper-shell outline-workbench ${props.locked ? "readonly" : ""}`}>
      <aside className="laper-rail" aria-label="大纲导航">
        <div className="laper-rail-brand">
          <strong>{props.plan.title || "故事大纲"}</strong>
          <span>大纲工作台</span>
        </div>
        <nav className="laper-rail-nav">
          {SECTIONS.map((item) => (
            <div className="laper-rail-tree-group" key={item.id}>
              <button
                aria-expanded={expandedSection === item.id}
                className={section === item.id ? "active" : ""}
                type="button"
                onClick={() => {
                  setSection(item.id);
                  setActiveIndex(0);
                  setExpandedSection((current) => current === item.id ? null : item.id);
                }}
              >
                <span>{item.label}</span>
                <span className="laper-rail-tree-meta">
                  <em>
                    {item.id === "phases"
                      ? props.plan.story_progression.length
                      : item.id === "endings"
                        ? props.plan.endings.length
                        : props.plan.characters.length}
                  </em>
                  <b aria-hidden="true">{expandedSection === item.id ? "⌄" : "›"}</b>
                </span>
              </button>
              {expandedSection === item.id && (
                <ol className="laper-rail-list laper-rail-tree-list">
                  {Array.from({ length: item.id === "phases" ? props.plan.story_progression.length : item.id === "endings" ? props.plan.endings.length : props.plan.characters.length }, (_, index) => (
                    <li key={`${item.id}-${index}`}>
                      <button
                        className={section === item.id && activeIndex === index ? "active" : ""}
                        type="button"
                        onClick={() => {
                          setSection(item.id);
                          setActiveIndex(index);
                          document.getElementById(`laper-block-${item.id}-${index}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
                        }}
                      >
                        <span>{index + 1}</span>
                        {blockLabel(item.id, props.plan, index)}
                      </button>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          ))}
        </nav>
      </aside>

      <section className="laper-canvas-wrap">
        {props.locked && (
          <div className="readonly-banner">
            {props.autoMode ? "Auto 模式正在自动生成完整游戏，大纲为只读状态。" : "大纲已确认，当前为只读状态。"}
          </div>
        )}

        <div className="laper-toolbar" role="toolbar" aria-label="大纲编辑工具栏">
          {SECTIONS.map((item) => (
            <button
              className={section === item.id ? "active" : ""}
              key={item.id}
              type="button"
              onClick={() => {
                setSection(item.id);
                setActiveIndex(0);
              }}
            >
              {item.label}
            </button>
          ))}
          <span className="laper-toolbar-divider" />
          <button className="laper-tool" type="button" disabled={disabled} onClick={addBlankBlock}>
            + 空白块
          </button>
          <input
            className="laper-brief-input"
            disabled={disabled}
            value={briefValue}
            onChange={(event) => setBriefValue(event.target.value)}
            placeholder={
              section === "phases"
                ? "简述想补充的阶段，AI 生成后加入列表"
                : section === "endings"
                  ? "简述想补充的结局"
                  : "简述想补充的角色"
            }
            onKeyDown={(event) => {
              if (event.key === "Enter" && !disabled) {
                event.preventDefault();
                addWithAi();
              }
            }}
          />
          <button className="laper-tool accent" type="button" disabled={disabled} onClick={addWithAi}>
            AI 生成
          </button>
        </div>

        <div className="laper-shortcuts" aria-hidden="true">
          <span>拖动 ⋮⋮ 排序</span>
          <span>Enter AI 生成</span>
          <span>点击左侧列表定位</span>
        </div>

        <div className="laper-canvas">
          <header className="laper-canvas-head">
            <div>
              <h2>{sectionMeta.label}</h2>
              <p>{sectionMeta.hint}</p>
            </div>
            <span>{sectionCount} 项</span>
          </header>

          <div
            className="laper-block-stack"
            onDragOver={(event) => {
              event.preventDefault();
              updateDragAutoScroll(event.clientY);
            }}
          >
            {pendingBrief && <PendingCard title={`AI 正在生成${sectionMeta.label}`} />}

            {section === "phases" &&
              props.plan.story_progression.map((step, index) => (
                <LaperBlock
                  active={activeIndex === index}
                  disabled={disabled}
                  dragIndex={dragIndex}
                  id={`laper-block-phases-${index}`}
                  index={index}
                  key={`${step.id}-${index}`}
                  label={step.id || `phase${index}`}
                  onActivate={() => setActiveIndex(index)}
                  onDrop={reorderSection}
                  onRemove={() => removeAt(index)}
                  setDragIndex={setDragIndex}
                  updateDragAutoScroll={updateDragAutoScroll}
                  stopDragAutoScroll={stopDragAutoScroll}
                  startPointerDrag={startPointerDrag}
                  movePointerDrag={movePointerDrag}
                  finishPointerDrag={finishPointerDrag}
                  dropHint={dropHint}
                  tag={step.strtype === "branch" ? "分支" : "主线"}
                >
                  <input
                    className="laper-block-title"
                    disabled={disabled}
                    value={step.name}
                    onChange={(event) => {
                      const next = [...props.plan.story_progression];
                      next[index] = { ...step, name: event.target.value };
                      props.updatePlan({ ...props.plan, story_progression: next });
                    }}
                    placeholder="阶段名称"
                  />
                  <textarea
                    className="laper-block-body"
                    disabled={disabled}
                    value={step.content}
                    onChange={(event) => {
                      const next = [...props.plan.story_progression];
                      next[index] = { ...step, content: event.target.value };
                      props.updatePlan({ ...props.plan, story_progression: next });
                    }}
                    placeholder="阶段内容：这一节点发生什么、推动什么矛盾"
                  />
                  <textarea
                    className="laper-block-note"
                    disabled={disabled}
                    value={step.narrative_target}
                    onChange={(event) => {
                      const next = [...props.plan.story_progression];
                      next[index] = { ...step, narrative_target: event.target.value };
                      props.updatePlan({ ...props.plan, story_progression: next });
                    }}
                    placeholder="叙事目标"
                  />
                  <div className="laper-block-meta">
                    <select
                      disabled={disabled}
                      value={step.strtype || "main"}
                      onChange={(event) => {
                        const next = [...props.plan.story_progression];
                        next[index] = { ...step, strtype: event.target.value };
                        props.updatePlan({ ...props.plan, story_progression: next });
                      }}
                    >
                      <option value="main">主线</option>
                      <option value="branch">分支</option>
                    </select>
                  </div>
                </LaperBlock>
              ))}

            {section === "endings" &&
              props.plan.endings.map((ending, index) => (
                <LaperBlock
                  active={activeIndex === index}
                  disabled={disabled}
                  dragIndex={dragIndex}
                  id={`laper-block-endings-${index}`}
                  index={index}
                  key={`${ending.ending_type}-${index}`}
                  label={`ending ${index + 1}`}
                  onActivate={() => setActiveIndex(index)}
                  onDrop={reorderSection}
                  onRemove={() => removeAt(index)}
                  setDragIndex={setDragIndex}
                  updateDragAutoScroll={updateDragAutoScroll}
                  stopDragAutoScroll={stopDragAutoScroll}
                  startPointerDrag={startPointerDrag}
                  movePointerDrag={movePointerDrag}
                  finishPointerDrag={finishPointerDrag}
                  dropHint={dropHint}
                  tag="结局"
                >
                  <input
                    className="laper-block-title"
                    disabled={disabled}
                    value={ending.ending_type}
                    onChange={(event) => {
                      const next = [...props.plan.endings];
                      next[index] = { ...ending, ending_type: event.target.value };
                      props.updatePlan({ ...props.plan, endings: next });
                    }}
                    placeholder="结局类型"
                  />
                  <textarea
                    className="laper-block-body"
                    disabled={disabled}
                    value={ending.description}
                    onChange={(event) => {
                      const next = [...props.plan.endings];
                      next[index] = { ...ending, description: event.target.value };
                      props.updatePlan({ ...props.plan, endings: next });
                    }}
                    placeholder="结局描述：玩家如何抵达、情绪与主题落点"
                  />
                </LaperBlock>
              ))}

            {section === "characters" &&
              props.plan.characters.map((character, index) => (
                <LaperBlock
                  active={activeIndex === index}
                  disabled={disabled}
                  dragIndex={dragIndex}
                  id={`laper-block-characters-${index}`}
                  index={index}
                  key={`${character.id}-${index}`}
                  label={character.id}
                  onActivate={() => setActiveIndex(index)}
                  onDrop={reorderSection}
                  onRemove={() => removeAt(index)}
                  setDragIndex={setDragIndex}
                  updateDragAutoScroll={updateDragAutoScroll}
                  stopDragAutoScroll={stopDragAutoScroll}
                  startPointerDrag={startPointerDrag}
                  movePointerDrag={movePointerDrag}
                  finishPointerDrag={finishPointerDrag}
                  dropHint={dropHint}
                  tag="角色"
                >
                  <input
                    className="laper-block-title"
                    disabled={disabled}
                    value={character.name}
                    onChange={(event) => {
                      const next = [...props.plan.characters];
                      next[index] = { ...character, name: event.target.value };
                      props.updatePlan({ ...props.plan, characters: next });
                    }}
                    placeholder="角色名称"
                  />
                  <textarea
                    className="laper-block-body"
                    disabled={disabled}
                    value={character.personality}
                    onChange={(event) => {
                      const next = [...props.plan.characters];
                      next[index] = { ...character, personality: event.target.value };
                      props.updatePlan({ ...props.plan, characters: next });
                    }}
                    placeholder="性格"
                  />
                  <textarea
                    className="laper-block-note"
                    disabled={disabled}
                    value={character.motivation}
                    onChange={(event) => {
                      const next = [...props.plan.characters];
                      next[index] = { ...character, motivation: event.target.value };
                      props.updatePlan({ ...props.plan, characters: next });
                    }}
                    placeholder="动机"
                  />
                </LaperBlock>
              ))}

            {!pendingBrief && sectionCount === 0 && (
              <div className="laper-empty">
                <p>还没有{sectionMeta.label}。点击「+ 空白块」手动添加，或输入简述后 AI 生成。</p>
              </div>
            )}
          </div>
        </div>
      </section>

      <aside className="laper-inspector outline-side">
        <LaperInspectorShell
          eyebrow="信息"
          title="大纲概览"
          stats={[
            { label: "阶段", value: props.plan.story_progression.length },
            { label: "结局", value: props.plan.endings.length },
            { label: "角色", value: props.plan.characters.length }
          ]}
          note={props.flowSyncing ? "流程图自动同步中..." : props.planDirty ? "修改后会自动同步流程图" : "流程图已同步"}
          footer={
            <>
              <button className="btn outline" type="button" disabled={disabled || !props.planDirty} onClick={props.savePlan}>
                保存大纲
              </button>
              <button className="btn outline" type="button" onClick={openFlowPreview}>
                查看流程图
              </button>
              <button
                className={`btn primary ${props.retryAction ? "retry-action" : ""}`}
                type="button"
                disabled={props.retryAction ? props.busy : disabled}
                onClick={props.retryAction || props.nextToScenes}
              >
                {props.retryAction ? <span aria-hidden="true">↻</span> : null}
                {props.busy && props.retryAction
                  ? "正在重试..."
                  : props.retryLabel || (props.locked ? "大纲已确认" : "确认并生成下一步")}
              </button>
            </>
          }
        >
          <div className="laper-meta-list">
            <div className="laper-meta-item">
              <span>标题</span>
              <strong>{props.plan.title || "未命名"}</strong>
            </div>
            <div className="laper-meta-item">
              <span>主题</span>
              <p>{props.plan.theme || "未填写"}</p>
            </div>
            <div className="laper-meta-item">
              <span>故事弧</span>
              <p>{props.plan.story_arc || "未填写"}</p>
            </div>
          </div>
        </LaperInspectorShell>
      </aside>

      {props.renderFlowModal(showFlowModal, () => setShowFlowModal(false))}
    </section>
  );
}

function LaperBlock(props: {
  id: string;
  index: number;
  label: string;
  tag: string;
  active: boolean;
  disabled: boolean;
  dragIndex: number | null;
  setDragIndex: (value: number | null) => void;
  updateDragAutoScroll: (pointerY: number) => void;
  stopDragAutoScroll: () => void;
  startPointerDrag: (index: number, pointerId: number, pointerY: number) => void;
  movePointerDrag: (pointerId: number, pointerX: number, pointerY: number) => void;
  finishPointerDrag: (pointerId: number) => void;
  dropHint: { index: number; placement: "before" | "after" } | null;
  onActivate: () => void;
  onDrop: (from: number, to: number) => void;
  onRemove: () => void;
  children: React.ReactNode;
}) {
  const dragging = props.dragIndex === props.index;

  return (
    <article
      className={`laper-block ${props.active ? "active" : ""} ${dragging ? "dragging" : ""} ${!dragging && props.dropHint?.index === props.index ? `drop-${props.dropHint.placement}` : ""}`}
      id={props.id}
      data-laper-outline-index={props.index}
      onClick={props.onActivate}
      onDragOver={(event) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
        props.updateDragAutoScroll(event.clientY);
      }}
      onDrop={(event) => {
        event.preventDefault();
        const from = Number(event.dataTransfer.getData("text/plain"));
        props.setDragIndex(null);
        props.stopDragAutoScroll();
        if (!Number.isNaN(from)) props.onDrop(from, props.index);
      }}
    >
      <button
        className="laper-drag-handle"
        type="button"
        aria-label="拖动排序"
        disabled={props.disabled}
        onPointerDown={(event) => {
          if (event.button !== 0) return;
          event.preventDefault();
          event.currentTarget.setPointerCapture(event.pointerId);
          props.startPointerDrag(props.index, event.pointerId, event.clientY);
        }}
        onPointerMove={(event) => {
          props.movePointerDrag(event.pointerId, event.clientX, event.clientY);
        }}
        onPointerUp={(event) => {
          props.finishPointerDrag(event.pointerId);
          event.currentTarget.releasePointerCapture(event.pointerId);
        }}
        onPointerCancel={(event) => {
          props.finishPointerDrag(event.pointerId);
        }}
      >
        ⋮⋮
      </button>
      <div className="laper-block-content">
        <div className="laper-block-head">
          <span>{props.label}</span>
          <em>{props.tag}</em>
          <button
            className="laper-block-delete"
            type="button"
            disabled={props.disabled}
            onClick={(event) => {
              event.stopPropagation();
              props.onRemove();
            }}
          >
            删除
          </button>
        </div>
        {props.children}
      </div>
    </article>
  );
}

function PendingCard({ title }: { title: string }) {
  return (
    <article className="laper-block pending-card" aria-live="polite" aria-busy="true">
      <div className="pending-spinner" aria-hidden="true" />
      <strong>{title}</strong>
    </article>
  );
}
