/**
 * The only script injected into untrusted works. It runs INSIDE the opaque-origin
 * sandbox. It contains no camera, network, token, or parent-page RPC access.
 */
export const BRIDGE_BOOTSTRAP = String.raw`(()=>{
"use strict";
if(window.NarrativeGesture && window.NarrativeGesture.version===1)return;
const origin=document.currentScript?.getAttribute("data-parent-origin");
let port=null,session="",recvSeq=-1,status="off",dwell=null,dwellFired=false;
const listeners=new Map();
const types=["pointer","pinch","rotate","swipe","reset","status"];
function clearDwell(){dwell=null;dwellFired=false;}
function canClick(el){
  return el && el.isConnected && !el.disabled && !el.closest("[hidden],[inert],[aria-hidden='true']") &&
    el.getClientRects().length>0 && getComputedStyle(el).visibility!=="hidden";
}
function dwellPointer(e){
  if(!e.visible || e.pose!=="point"){clearDwell();return;}
  const node=document.elementFromPoint(e.x*innerWidth,e.y*innerHeight);
  const target=node?.closest?.("[data-gesture-dwell]");
  if(!canClick(target)){clearDwell();return;}
  const now=performance.now();
  if(!dwell || dwell.target!==target || Math.hypot(dwell.x-e.x,dwell.y-e.y)>0.045){
    dwell={target,x:e.x,y:e.y,t:now};dwellFired=false;
  } else if(!dwellFired && now-dwell.t>=700){
    dwellFired=true;target.click();
  }
}
function valid(e){
  if(!e || typeof e!=="object" || !types.includes(e.kind))return false;
  const num=n=>typeof n==="number"&&Number.isFinite(n)&&n>=0&&n<=1;
  switch(e.kind){
    case "pointer":return typeof e.visible==="boolean"&&(!e.visible||(num(e.x)&&num(e.y)));
    case "pinch":return ["start","move","end"].includes(e.phase)&&num(e.x)&&num(e.y);
    case "rotate":return typeof e.deltaX==="number"&&Number.isFinite(e.deltaX)&&Math.abs(e.deltaX)<=0.1&&num(e.x)&&num(e.y);
    case "swipe":return e.direction==="left"||e.direction==="right";
    case "reset":return e.reason==="open-hold";
    case "status":return ["off","starting","running","stopping","error"].includes(e.state);
  }
}
function deliver(e){
  if(e.kind==="pointer")dwellPointer(e);
  else if(e.kind==="swipe"||e.kind==="pinch"||e.kind==="reset"||(e.kind==="status"&&e.state!=="running"))clearDwell();
  if(e.kind==="status")status=e.state;
  for(const callback of listeners.get(e.kind)||[]){
    try{callback(e);}catch(error){console.error("Gesture work listener failed");}
  }
}
const api=Object.freeze({
  version:1,
  on(kind,callback){
    if(!types.includes(kind)||typeof callback!=="function")return ()=>{};
    let set=listeners.get(kind);if(!set){set=new Set();listeners.set(kind,set);}
    set.add(callback);return ()=>set.delete(callback);
  },
  getStatus(){return status;}
});
Object.defineProperty(window,"NarrativeGesture",{value:api,configurable:false,writable:false});
window.addEventListener("message",event=>{
  if(event.source!==window.parent||event.origin!==origin)return;
  const data=event.data;
  if(!data||data.channel!=="nar-gesture"||data.v!==1||data.type!=="NAR_GESTURE_CONNECT"||
    typeof data.sessionId!=="string"||data.sessionId.length>100||!event.ports?.[0])return;
  port?.close();clearDwell();status="off";session=data.sessionId;recvSeq=-1;
  port=event.ports[0];
  const current=port;
  current.onmessage=msg=>{
    if(current!==port)return;
    const m=msg.data;
    try{if(JSON.stringify(m).length>512)return;}catch{return;}
    if(!m||m.channel!=="nar-gesture"||m.v!==1||m.sessionId!==session||
      m.type!=="EVENT"||!Number.isSafeInteger(m.seq)||m.seq<=recvSeq||!valid(m.event))return;
    recvSeq=m.seq;deliver(m.event);
  };
  current.start();
  current.postMessage({channel:"nar-gesture",v:1,sessionId:session,seq:0,type:"READY",info:{bridgeVersion:1}});
});
window.addEventListener("pagehide",()=>{clearDwell();port?.close();port=null;status="off";});
})();`;
