import type { GestureAction, GestureBindings, GestureManifest, NarActionEvent } from "./gesture-types";
import { GESTURE_PROTOCOL, validBindings, validActionData } from "./gesture-types";

/** Per-iframe, one-use MessageChannel. Frame never gains parent or camera APIs. */
export class GestureBridge {
  private port: MessagePort | null = null;
  private session = "";
  private seq = 0;
  private ready = false;
  private bound: GestureBindings | null = null;
  private onReady: (bindings: GestureBindings) => void;
  private onHover: (hasTarget:boolean) => void;
  constructor(private iframe: HTMLIFrameElement, private manifest: GestureManifest,
              onReady:(bindings:GestureBindings)=>void,onHover:(hasTarget:boolean)=>void) {
    this.onReady = onReady; this.onHover = onHover;
  }
  handleHello(event: MessageEvent) {
    if (event.source !== this.iframe.contentWindow) return;
    const message = event.data;
    if (!message || typeof message !== "object" || message.protocol !== GESTURE_PROTOCOL ||
        message.type !== "hello" || message.schemaVersion !== "0.2.0" ||
        !validBindings(message.bindings,this.manifest)) return;
    this.dispose();
    this.bound = {schemaVersion:"0.2.0",bindings:message.bindings};
    this.session = crypto.randomUUID();
    const channel = new MessageChannel();
    this.port = channel.port1;
    const expectedSession = this.session;
    this.port.onmessage = e => {
      const packet = e.data;
      if (!packet || packet.protocol !== GESTURE_PROTOCOL || packet.session !== expectedSession) return;
      if (packet.type === "ready" && !this.ready) {
        this.ready = true;
        this.onReady(this.bound!);
      } else if (packet.type === "hover" && this.ready && typeof packet.hasTarget === "boolean") {
        this.onHover(packet.hasTarget);
      }
    };
    this.port.start();
    // Opaque sandbox origins have no stable targetOrigin; target only this iframe window.
    this.iframe.contentWindow?.postMessage(
      {protocol:GESTURE_PROTOCOL,type:"init",session:this.session},"*",[channel.port2]);
  }
  send(action: GestureAction,event: NarActionEvent) {
    if (!this.port || !this.ready || !validActionData(event) ||
        !this.bound?.bindings.some(b => b.action === action && b.phases.includes(event.phase))) return;
    this.port.postMessage({protocol:GESTURE_PROTOCOL,type:"command",session:this.session,seq:++this.seq,action,event});
  }
  dispose() { this.port?.close(); this.port = null; this.ready = false; this.session = ""; this.bound = null; this.seq = 0; }
}
