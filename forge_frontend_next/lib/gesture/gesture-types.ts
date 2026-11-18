export type GestureId = "pinch" | "fist_rotate" | "index_pointer" | "open_palm_hold";
export type GesturePhase = "start" | "move" | "end" | "click" | "swipe" | "trigger";
export type GestureAction = "rotate" | "grab" | "drag" | "pan" | "hover" | "click" | "swipe" | "select" | "reset";
export type Direction = "left" | "right" | "up" | "down";
export type NarActionEvent = { phase: GesturePhase; x?: number; y?: number; dx?: number; dy?: number; direction?: Direction };
export type GestureEvent = { gestureId: GestureId; phase: GesturePhase; timestamp: number; data: Omit<NarActionEvent, "phase"> };
export type GestureBinding = { gesture: GestureId; phases: GesturePhase[]; action: GestureAction };
export type GestureBindings = { schemaVersion: "0.2.0"; bindings: GestureBinding[] };
export type ManifestEntry = { id: GestureId; rule: string; hands: 1; events: GesturePhase[]; outputs: string[]; suggestedActions: GestureAction[] };
export type GestureManifest = { schemaVersion: "0.2.0"; provider: string; gestures: ManifestEntry[] };
export type Landmark = { x: number; y: number; z?: number };
export type HandFeatures = { x: number; y: number; cx: number; cy: number; pinchRatio: number; fist: boolean; pointer: boolean; palm: boolean };
export const GESTURE_PROTOCOL = "nar.gesture/0.2";
export const ACTION_FIELDS: Record<GestureAction, string[]> = {
  rotate: ["dx","dy"], grab:["x","y"], drag:["dx","dy"], pan:["dx","dy"],
  hover:["x","y"], click:["x","y"], swipe:["direction"], select:["x","y"], reset:[]
};
export function validBindings(value: unknown, manifest: GestureManifest): value is GestureBinding[] {
  if (!Array.isArray(value) || value.length < 1 || value.length > 12 || manifest.schemaVersion !== "0.2.0") return false;
  const seen = new Set<string>();
  return value.every(b => {
    if (!b || typeof b !== "object" || !("gesture" in b) || !("action" in b) || !("phases" in b)) return false;
    if (Object.keys(b).sort().join(",") !== "action,gesture,phases") return false;
    const item = manifest.gestures.find(g => g.id === b.gesture);
    if (!item || typeof b.action !== "string" || !item.suggestedActions.includes(b.action as GestureAction) ||
        !Object.hasOwn(ACTION_FIELDS, b.action) || !Array.isArray(b.phases) || !b.phases.length || b.phases.length > 6) return false;
    const phases = b.phases as unknown[];
    if (!phases.every(p => typeof p === "string" && item.events.includes(p as GesturePhase))) return false;
    if (b.action === "reset" && (phases.length !== 1 || phases[0] !== "trigger")) return false;
    if ((b.action === "click" || b.action === "swipe") && !phases.includes(b.action)) return false;
    return phases.every(p => {
      const key = b.gesture + ":" + p;
      if (seen.has(key)) return false;
      seen.add(key);
      return !["move", "click", "swipe", "trigger"].includes(p as string) ||
        ACTION_FIELDS[b.action as GestureAction].every(field => item.outputs.includes(field));
    });
  });
}
export function validActionData(event: NarActionEvent): boolean {
  if (!event || !["start","move","end","click","swipe","trigger"].includes(event.phase)) return false;
  for (const field of ["x","y","dx","dy"] as const) {
    const n = event[field];
    if (n !== undefined && (!Number.isFinite(n) || Math.abs(n) > 2 || (field === "x" || field === "y") && (n < 0 || n > 1))) return false;
  }
  return event.direction === undefined || ["left","right","up","down"].includes(event.direction);
}
