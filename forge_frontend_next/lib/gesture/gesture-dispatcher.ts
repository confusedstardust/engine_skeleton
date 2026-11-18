import type { GestureBindings, GestureEvent, GestureManifest, NarActionEvent, GestureAction } from "./gesture-types";
import { validBindings, validActionData } from "./gesture-types";

export class GestureBindingDispatcher {
  private lookup = new Map<string, GestureAction>();
  constructor(bindings: GestureBindings, manifest: GestureManifest, private send: (action: GestureAction, event: NarActionEvent) => void) {
    if (bindings.schemaVersion !== "0.2.0" || !validBindings(bindings.bindings, manifest)) {
      throw new Error("Invalid GestureBindings");
    }
    for (const b of bindings.bindings) for (const phase of b.phases) this.lookup.set(b.gesture + ":" + phase, b.action);
  }
  dispatch(events: GestureEvent[]) {
    for (const e of events) {
      const action = this.lookup.get(e.gestureId + ":" + e.phase);
      if (!action) continue;
      const value: NarActionEvent = {phase:e.phase,...e.data};
      if (!validActionData(value)) continue;
      this.send(action,value);
    }
  }
}
