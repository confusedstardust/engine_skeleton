"use client";

import { useMemo, useState } from "react";
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
  renderFlowModal: (open: boolean, onClose: () => void) => React.ReactNode;
};

const SECTIONS: { id: OutlineSection; label: string; hint: string }[] = [
  { id: "phases", label: "故事阶段", hint: "拖动左侧把手可调整顺序，直接点击文本即可修改。" },
  { id: "endings", label: "结局节点", hint: "每个结局会在下一步生成独立场景。" },
  { id: "characters", label: "角色阵容", hint: "可增删角色，并补充性格与动机。" }
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
  const [section, setSection] = useState<OutlineSection>("phases");
  const [activeIndex, setActiveIndex] = useState(0);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [showFlowModal, setShowFlowModal] = useState(false);
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

  function scrollToBlock(index: number) {
    setActiveIndex(index);
    document.getElementById(`laper-block-${section}-${index}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
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
    if (section === "phases") {
      props.updatePlan({ ...props.plan, story_progression: reorder(props.plan.story_progression, from, to) });
    } else if (section === "endings") {
      props.updatePlan({ ...props.plan, endings: reorder(props.plan.endings, from, to) });
    } else {
      props.updatePlan({ ...props.plan, characters: reorder(props.plan.characters, from, to) });
    }
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
              <em>
                {item.id === "phases"
                  ? props.plan.story_progression.length
                  : item.id === "endings"
                    ? props.plan.endings.length
                    : props.plan.characters.length}
              </em>
            </button>
          ))}
        </nav>
        <ol className="laper-rail-list">
          {Array.from({ length: sectionCount }, (_, index) => (
            <li key={`${section}-${index}`}>
              <button className={activeIndex === index ? "active" : ""} type="button" onClick={() => scrollToBlock(index)}>
                <span>{index + 1}</span>
                {blockLabel(section, props.plan, index)}
              </button>
            </li>
          ))}
        </ol>
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

          <div className="laper-block-stack">
            {pendingBrief && <PendingCard title={`正在生成${sectionMeta.label}`} brief={pendingBrief} />}

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
              <button className="btn primary" type="button" disabled={disabled} onClick={props.nextToScenes}>
                {props.locked ? "大纲已确认" : "确认并生成下一步"}
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
  onActivate: () => void;
  onDrop: (from: number, to: number) => void;
  onRemove: () => void;
  children: React.ReactNode;
}) {
  const dragging = props.dragIndex === props.index;

  return (
    <article
      className={`laper-block ${props.active ? "active" : ""} ${dragging ? "dragging" : ""}`}
      id={props.id}
      onClick={props.onActivate}
      onDragOver={(event) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
      }}
      onDrop={(event) => {
        event.preventDefault();
        const from = Number(event.dataTransfer.getData("text/plain"));
        props.setDragIndex(null);
        if (!Number.isNaN(from)) props.onDrop(from, props.index);
      }}
    >
      <button
        className="laper-drag-handle"
        type="button"
        aria-label="拖动排序"
        disabled={props.disabled}
        draggable={!props.disabled}
        onDragStart={(event) => {
          event.dataTransfer.setData("text/plain", String(props.index));
          event.dataTransfer.effectAllowed = "move";
          props.setDragIndex(props.index);
        }}
        onDragEnd={() => props.setDragIndex(null)}
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

function PendingCard({ title, brief }: { title: string; brief: string }) {
  return (
    <article className="laper-block pending-card">
      <div className="pending-spinner" aria-hidden="true" />
      <strong>{title}</strong>
      <p>{brief}</p>
    </article>
  );
}
