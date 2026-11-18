import type {GestureEvent} from "./protocol";
import {GESTURE_MANIFEST as M} from "./manifest";
type Point={x:number;y:number};
type Hand={pose:string|null;pinch:number;heldMs:number;landmarks?:Point[];features:{center:Point}};
export type GestureFrame={t:number;hands:Hand[]};
const clamp=(n:number,min=0,max=1)=>Math.min(max,Math.max(min,n));
function screen(p:Point):Point {
  const r=M.region;
  return {x:clamp((p.x-r.x0)/(r.x1-r.x0)),y:clamp((p.y-r.y0)/(r.y1-r.y0))};
}
/** Stateless w.r.t. DOM: suitable for synthetic tests and trusted runtime. */
export class GestureAdapter {
  private pressed=false; private previous:({pos:Point;centerX:number;pose:string|null})|null=null;
  private swipeStart:({pos:Point;t:number})|null=null; private swipeCooldown=0;
  private openFired=false; private lastPointerT=-Infinity; private visible=false;
  constructor(private readonly emit:(event:GestureEvent)=>void){}
  release(){
    if(this.pressed) this.emit({kind:"pinch",phase:"end",...(this.previous?.pos||{x:.5,y:.5})});
    this.pressed=false;this.previous=null;this.swipeStart=null;this.openFired=false;
    if(this.visible){this.emit({kind:"pointer",visible:false});this.visible=false;}
  }
  consume(frame:GestureFrame){
    const h=frame.hands[0];
    if(!h){this.release();return;}
    const pos=screen(h.landmarks?.[8] || h.features.center);
    const centerX=screen(h.features.center).x;
    const pose=h.pose;
    const pinching=this.pressed?h.pinch>M.pinchExit:h.pinch>=M.pinchEnter;
    // Exclusive: a fist rotates, a pinch drags, only a pointing finger swipes.
    const rotating=pose==="fist"&&!pinching;
    const pointing=pose==="point"&&!pinching;
    const mappedPose=pinching?"pinch":pose==="point"||pose==="fist"||pose==="open"?pose:"other";
    if(frame.t-this.lastPointerT>=1000/M.pointerMaxHz){
      this.emit({kind:"pointer",visible:true,...pos,pose:mappedPose});
      this.lastPointerT=frame.t;this.visible=true;
    }
    if(pinching&&!this.pressed) this.emit({kind:"pinch",phase:"start",...pos});
    if(pinching) this.emit({kind:"pinch",phase:"move",...pos});
    if(!pinching&&this.pressed) this.emit({kind:"pinch",phase:"end",...pos});
    this.pressed=pinching;
    if(rotating&&this.previous?.pose==="fist"){
      const deltaX=clamp(centerX-this.previous.centerX,-M.rotateDeltaLimit,M.rotateDeltaLimit);
      if(Math.abs(deltaX)>.002) this.emit({kind:"rotate",deltaX,...pos});
    }
    this.previous={pos,centerX,pose:rotating?"fist":pose};
    if(pose==="open"&&!pinching&&h.heldMs>=M.openHoldMs&&!this.openFired){
      this.emit({kind:"reset",reason:"open-hold"});this.openFired=true;
    }
    if(pose!=="open")this.openFired=false;
    if(!pointing){this.swipeStart=null;return;}
    const old=this.swipeStart;
    if(!old||frame.t-old.t>M.swipeMaxMs||Math.abs(pos.y-old.pos.y)>M.swipeMaxY){
      this.swipeStart={pos,t:frame.t};return;
    }
    const delta=pos.x-old.pos.x,elapsed=frame.t-old.t;
    if(elapsed>=M.swipeMinMs&&Math.abs(delta)>=M.swipeMinX&&frame.t>=this.swipeCooldown){
      this.emit({kind:"swipe",direction:delta<0?"left":"right"});
      this.swipeStart=null;this.swipeCooldown=frame.t+M.swipeCooldownMs;
    }
  }
}
