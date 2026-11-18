/** NarGestureBridge v1: no camera data, network requests or privileged RPC. */
export const NAR_GESTURE_PROTOCOL = 1 as const;
export type GestureEvent =
  | {kind:"pointer"; visible:boolean; x?:number; y?:number; pose?:"point"|"fist"|"open"|"pinch"|"other"}
  | {kind:"pinch"; phase:"start"|"move"|"end"; x:number; y:number}
  | {kind:"rotate"; deltaX:number; x:number; y:number}
  | {kind:"swipe"; direction:"left"|"right"}
  | {kind:"reset"; reason:"open-hold"}
  | {kind:"status"; state:"off"|"starting"|"running"|"stopping"|"error"; code?:string};
export type BridgeEnvelope = {channel:"nar-gesture";v:1;sessionId:string;seq:number;type:"EVENT";event:GestureEvent}
  | {channel:"nar-gesture";v:1;sessionId:string;seq:number;type:"READY"|"DISPOSED";info?:{bridgeVersion:number}};
const coordinate = (v:unknown):v is number => typeof v==="number" && Number.isFinite(v) && v>=0 && v<=1;
const smallNumber = (v:unknown):v is number => typeof v==="number" && Number.isFinite(v) && v>=-0.1 && v<=0.1;
export function isGestureEvent(raw:unknown):raw is GestureEvent {
  if(!raw || typeof raw!=="object") return false;
  const e=raw as Record<string,unknown>;
  switch(e.kind){
    case "pointer": return typeof e.visible==="boolean" &&
      (!e.visible || (coordinate(e.x)&&coordinate(e.y))) &&
      (e.pose===undefined || ["point","fist","open","pinch","other"].includes(String(e.pose)));
    case "pinch": return ["start","move","end"].includes(String(e.phase)) && coordinate(e.x) && coordinate(e.y);
    case "rotate": return smallNumber(e.deltaX) && coordinate(e.x) && coordinate(e.y);
    case "swipe": return e.direction==="left" || e.direction==="right";
    case "reset": return e.reason==="open-hold";
    case "status": return ["off","starting","running","stopping","error"].includes(String(e.state)) &&
      (e.code===undefined || (typeof e.code==="string" && e.code.length<=64));
    default: return false;
  }
}
export function validControlMessage(raw:unknown, sessionId:string, previousSeq:number):raw is BridgeEnvelope {
  if(!raw || typeof raw!=="object") return false;
  try { if(JSON.stringify(raw).length>512) return false; }catch {return false;}
  const m=raw as Partial<BridgeEnvelope>;
  return m.channel==="nar-gesture" && m.v===NAR_GESTURE_PROTOCOL && m.sessionId===sessionId &&
    Number.isSafeInteger(m.seq) && Number(m.seq)>previousSeq && Number(m.seq)<=100000000 &&
    (m.type==="READY" || m.type==="DISPOSED") && !("event" in m);
}
