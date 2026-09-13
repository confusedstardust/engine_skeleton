export type InteractionKind = 'investigation' | 'qte' | 'movement';
export type Outcome = 'success' | 'failed' | 'skipped';
export type Scalar = string | number | boolean;
export type PauseReason = 'menu' | 'hidden' | 'blur' | 'manual';
export type InteractionLifecycle = 'idle' | 'loading' | 'ready' | 'running' | 'paused' | 'settling' | 'completed' | 'error' | 'cancelled';

export interface InteractionResult { outcome: Outcome; values: Record<string, Scalar>; }
export interface Rect { x: number; y: number; width: number; height: number; }
export interface InvestigationConfig {
  schemaVersion: 1; id: string; type: 'investigation'; sceneFile: string; title: string; resumePolicy: 'resume'; resultBindings: Record<string, string>;
  payload: { image: string; imageSize: { width: number; height: number }; fit: 'contain'; lens: { enabled: boolean; zoom: number; radiusCssPx: number }; hotspots: Array<{ id: string; rect: Rect; title: string; description: string }>; completion: { requiredIds: string[] }; allowSkip: boolean; hintAfterMs: number };
}
export interface QteConfig {
  schemaVersion: 1; id: string; type: 'qte'; sceneFile: string; title: string; resumePolicy: 'restart'; resultBindings: Record<string, string>;
  payload: { mode: 'sequence'; steps: Array<{ action: string; windowMs: number }>; bindings: Record<string, string[]>; wrongAction: 'fail'; showStartButton: boolean; allowSkip: boolean; timeScale: number };
}
export interface MovementConfig {
  schemaVersion: 1; id: string; type: 'movement'; sceneFile: string; title: string; resumePolicy: 'resume'; resultBindings: Record<string, string>;
  payload: { target: string; coordinateSpace: 'stage-design'; designSize: { width: number; height: number }; initialAnchor: { x: number; y: number }; bounds: Rect; speed: number; goal: { id: string; rect: Rect }; completionMode: 'confirm-in-goal'; persistPosition: boolean; allowSkip: boolean };
}
export type InteractionConfig = InvestigationConfig | QteConfig | MovementConfig;
export type ModuleSnapshot =
  | { type: 'investigation'; foundIds: string[]; activeCardId: string | null; activeElapsedMs: number }
  | { type: 'qte'; stepIndex: number; remainingMs: number; completedSteps: number; effectiveTimeScale: number }
  | { type: 'movement'; originalTransform: Record<string, Scalar> | null; currentAnchor: { x: number; y: number }; reachedGoalId: string | null };
export interface InteractionSaveState {
  schemaVersion: 1; contentVersion: string; active: null | { instanceId: string; nodeId: string; kind: InteractionKind; configPath: string; sceneUrl: string; enteredSentenceId: number; continueSentenceId: number; lifecycle: 'ready' | 'running' | 'paused'; resumePolicy: 'resume' | 'restart'; module: ModuleSnapshot };
  receipts: Record<string, InteractionResult>; pendingContinuation: null | { receiptId: string; sceneUrl: string; continueSentenceId: number };
}
export type InteractionAction = { type: 'pointerInspect'; hotspotId: string } | { type: 'confirmClue' } | { type: 'qteAction'; action: string } | { type: 'moveAxes'; x: number; y: number } | { type: 'confirmFinish' } | { type: 'start' } | { type: 'skip' };
export interface InteractionViewModel { lifecycle: InteractionLifecycle; config: InteractionConfig | null; snapshot: ModuleSnapshot | null; pauseReasons: PauseReason[]; error?: string; }
