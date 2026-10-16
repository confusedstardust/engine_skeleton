export type StoryStep = {
  id: string;
  name: string;
  content: string;
  narrative_target: string;
  music_mood?: "ordinary" | "peace" | "slow" | "soft" | "tense" | "warm";
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
  music_mood?: "happy" | "normal" | "sad" | "bad" | "terrible";
};

export type NarrativeNodeKind = "phase" | "ending" | "character";

export type GeneratedNarrativeNodeResponse = {
  kind: NarrativeNodeKind;
  node: StoryStep | NarrativeEnding | NarrativeCharacter;
  provider: "deepseek" | "mimo" | "kimi";
};

export type SyncNarrativeStructureResponse = {
  narrative_plan: NarrativePlan;
  narrative_structure: string;
  issues: { node: string; reason: string }[];
};

export type SyncNarrativeStructureOptions = {
  quiet?: boolean;
  force?: boolean;
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

export type ScenePlan = {
  scenes: {
    kind?: "Scene";
    scene_file: string;
    source_node: string;
    node_name: string;
    strtype: string;
  }[];
  endings: {
    kind?: "Ending";
    scene_file: string;
    ending_type: string;
    description: string;
  }[];
};

export type SceneDraft = {
  header: string;
  title: string;
  lines: SceneLine[];
  marker?: "Scene" | "Ending";
  sourceNode?: string;
  strtype?: string;
};

export type GameDesignDraftScene = SceneDraft & {
  marker: "Scene" | "Ending";
  sourceNode: string;
  endingType: string;
};

export type SceneLine = {
  id: string;
  kind: "narration" | "dialogue" | "command" | "choice" | "branch";
  speaker: string;
  text: string;
  rawPrefix: string;
  choices?: SceneChoice[];
  branchLabel?: string;
};

export type SceneChoice = {
  text: string;
  target: string;
  target_scene_file?: string;
  targetSceneFile?: string;
};
