import type { EditableScene, SceneLine } from "./laper-scene-workbench";

export function repairContinuationLabels<T extends EditableScene>(scenes: T[]): T[] {
  return scenes.map(scene => {
    const labels = new Set(scene.lines.filter(line => line.kind === "branch").map(line => line.branchLabel || line.text));
    const lines: SceneLine[] = [];
    let changed = false;
    for (const line of scene.lines) {
      lines.push(line);
      if (line.kind !== "choice") continue;
      for (const choice of line.choices || []) {
        const target = choice.target_scene_file || choice.targetSceneFile || choice.target;
        if (!/^continue_choice_[A-Za-z0-9_]+$/.test(target) || labels.has(target)) continue;
        labels.add(target);
        changed = true;
        lines.push({ id: `${line.id}-label-${target}`, kind: "branch", speaker: "分支", text: target, rawPrefix: "branch", branchLabel: target });
      }
    }
    return changed ? { ...scene, lines } : scene;
  });
}

export function insertionIndex(lines: SceneLine[], selectedId: string | null): number {
  const selected = lines.findIndex(line => line.id === selectedId);
  let index = selected < 0 ? lines.length : selected + 1;
  const selectedLine = lines[selected];
  if (selectedLine?.kind === "choice" && lines[index]?.kind === "branch") {
    const label = lines[index].branchLabel || lines[index].text;
    if (selectedLine.choices?.some(choice => (choice.target_scene_file || choice.targetSceneFile || choice.target) === label)) index++;
  }
  const terminal = lines.findIndex(isTerminalLine);
  return terminal < 0 ? index : Math.min(index, terminal);
}

export function keepContinuationLabelsTogether(lines: SceneLine[]): SceneLine[] {
  let result = [...lines];
  for (const choice of lines.filter(line => line.kind === "choice")) {
    const labels = result.filter(line => line.kind === "branch" && line.id.startsWith(`${choice.id}-label`) &&
      choice.choices?.some(option => (option.target_scene_file || option.targetSceneFile || option.target) === (line.branchLabel || line.text)));
    if (!labels.length) continue;
    result = result.filter(line => !labels.includes(line));
    result.splice(result.findIndex(line => line.id === choice.id) + 1, 0, ...labels);
  }
  return result;
}

export function jumpTarget(line: SceneLine): string | null {
  if (line.kind !== "command") return null;
  return /^changeScene\s*:\s*([A-Za-z0-9_-]+\.txt)\s*;?$/i.exec(line.text.trim())?.[1] ?? null;
}

export function isTerminalLine(line: SceneLine): boolean {
  return jumpTarget(line) !== null || (line.kind === "command" && /^end\s*;?$/i.test(line.text.trim())) ||
    (line.kind === "choice" && !!line.choices?.length && line.choices.every(choice => /\.txt$/i.test(choice.target_scene_file || choice.targetSceneFile || choice.target)));
}

// The edited scenes, not the original flowchart, are the source of truth.
export function validateSceneConnections(scenes: EditableScene[]): Record<string, string> {
  const errors: Record<string, string> = {};
  const files = new Set(scenes.map(scene => scene.header));
  for (const scene of scenes) {
    const labels = new Set(scene.lines.filter(line => line.kind === "branch").map(line => line.branchLabel || line.text));
    const lines = scene.lines.filter(line => line.kind === "choice" || line.text.trim());
    for (const [index, line] of lines.entries()) {
      const target = jumpTarget(line);
      if (target && !files.has(target)) errors[scene.header] = `跳转目标 ${target} 不存在，请重新选择场景。`;
      if (isTerminalLine(line) && index !== lines.length - 1) errors[scene.header] = "场景跳转或跨场景分支后还有内容，请将结束连接放在最后一行。";
      if (line.kind === "choice") {
        if (!line.choices?.length) errors[scene.header] = "互动分支没有选项，请添加选项并选择目标场景。";
        for (const choice of line.choices || []) {
          const dest = choice.target_scene_file || choice.targetSceneFile || choice.target;
          if (!choice.text.trim() || (!files.has(dest) && !labels.has(dest))) errors[scene.header] = "分支选项的文本或跳转目标无效，请检查每个选项。";
        }
      }
    }
    if (scene.marker !== "Ending" && (!lines.length || !isTerminalLine(lines[lines.length - 1]))) {
      errors[scene.header] ||= "场景结束时没有衔接：请在最后新增一行「场景跳转」，或添加跳转到具体场景的「互动分支」。";
    }
  }
  return errors;
}
