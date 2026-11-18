---
name: gesture-ar
description: Generate HTML learning games using the NarrativeOS opaque-iframe Gesture Runtime Bridge v1.
---

# NarrativeOS Gesture Runtime Bridge v1

## Architecture and hard boundaries
The trusted NarrativeOS parent owns camera, MediaPipe and a single tracker. The sandboxed HTML work receives only validated semantic events over a platform-injected `window.NarrativeGesture`. The generated work must NOT call getUserMedia, import MediaPipe/createHands/SDK, open arbitrary parent RPC, fetch a server or ask for camera permission. HTML is a single file with inline CSS/JS and `<body data-nar-gesture="v1">`. Never add iframe privileges, external dependencies or bypass the parent. Previewing a private/unpublished work supports the same gestures. Downloaded HTML has no Bridge and must still work with mouse/touch/keyboard.

## Public game API
```js
const g = window.NarrativeGesture;
const off = g?.on('pinch', e => { /* phase 'start'|'move'|'end'; x,y in 0..1 */ });
g?.on('rotate', e => { /* deltaX -0.1..0.1; x,y */ });
g?.on('pointer', e => { /* visible, x,y, pose */ });
g?.on('swipe', e => { /* direction 'left'|'right' */ });
g?.on('reset', e => { /* reason 'open-hold' */ });
g?.on('status', e => { /* state 'off'|'starting'|'running'|'stopping'|'error' */ });
g?.getStatus(); // off when not connected
// off?.() when a scene is destroyed
```
The platform bootstrap is installed before game scripts, and accepts pre-READY subscriptions. Do not hand-code MessageChannel. Parent may stop at any time: on status off/error or pointer.visible=false clear held drag/selection and show mouse fallback.

## Manifest (fixed semantics)
- pinch-drag: pinch strength hysteresis 0.72 enter / 0.36 release, emits pinch start/move/end with normalized x,y.
- fist-rotate: fist motion emits rotate deltaX, clamped +/-0.1, along with normalized x,y.
- index-pointer: point emits pointer coordinates. For DOM buttons, add `data-gesture-dwell`; platform child bootstrap hit-tests the local DOM and invokes click after 700ms stable motion within 0.045. Don't click arbitrary buttons.
- index-swipe: in point pose, horizontal distance >=0.18 over 120-650ms and vertical <=0.09; swipe left/right (650ms cooldown).
- open-palm-hold: open hand held >=900ms emits reset once. Pose exclusivity prevents pointing/swiping during pinch/fist.
Runtime thresholds are defined in frontend gesture-bridge/manifest.ts, not in this Skill.

## DOM example: draggable knowledge classification with one game input
```html
<body data-nar-gesture="v1">
  <h1>生物分类</h1><div id="tile" tabindex="0" style="touch-action:none;position:relative">哺乳动物：鲸鱼</div>
  <button id="check" data-gesture-dwell>放置并检查</button><output id="result"></output>
  <script>
  const tile=document.getElementById('tile'), result=document.getElementById('result');
  let start=null, offset=0;
  const game={
    begin(x){start=x;}, move(x){if(start===null)return;offset+=(x-start)*innerWidth;start=x;tile.style.left=offset+'px';},
    end(){start=null;}, reset(){start=null;offset=0;tile.style.left='0px';}
  };
  tile.onpointerdown=e=>{tile.setPointerCapture(e.pointerId);game.begin(e.clientX/innerWidth)};
  tile.onpointermove=e=>{if(e.buttons)game.move(e.clientX/innerWidth)};
  tile.onpointerup=game.end;tile.onpointercancel=game.end;
  tile.onkeydown=e=>{if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();game.begin(0);game.move(e.key==='ArrowRight'?.05:-.05);game.end();}};
  document.getElementById('check').onclick=()=>{result.textContent=offset>50?'分类成功':'请向右移动至正确区域'};
  window.NarrativeGesture?.on('pinch',e=>{if(e.phase==='start')game.begin(e.x);else if(e.phase==='move')game.move(e.x);else game.end()});
  window.NarrativeGesture?.on('reset',()=>game.reset());
  window.NarrativeGesture?.on('status',e=>{if(e.state!=='running')game.end()});
  </script>
</body>
```
For full lessons add an actual drop zone, score and completion conditions; this only illustrates shared input routing.

## Canvas example: normalized-to-local hit-test
```html
<body data-nar-gesture="v1">
  <canvas id="board" width="600" height="360" style="width:100%;max-width:600px;touch-action:none"></canvas>
  <button id="retry" data-gesture-dwell>重置</button><output id="feedback"></output>
  <script>
  const canvas=document.getElementById('board'),ctx=canvas.getContext('2d');
  let target={x:300,y:180},selected=false;
  const local=(x,y)=>{const r=canvas.getBoundingClientRect();return {
    x:(x-r.left)*canvas.width/r.width,y:(y-r.top)*canvas.height/r.height};};
  function render(){ctx.clearRect(0,0,600,360);ctx.fillRect(target.x-25,target.y-25,50,50);}
  const game={
    begin(p){selected=Math.hypot(p.x-target.x,p.y-target.y)<40;},
    move(p){if(selected){target=p;render()}},
    end(){selected=false;document.getElementById('feedback').textContent=target.x>450?'已到达目标轨道':'继续移动';},
    reset(){selected=false;target={x:300,y:180};render();}
  };
  canvas.onpointerdown=e=>{canvas.setPointerCapture(e.pointerId);game.begin(local(e.clientX,e.clientY))};
  canvas.onpointermove=e=>{if(e.buttons)game.move(local(e.clientX,e.clientY))};
  canvas.onpointerup=game.end;canvas.onpointercancel=game.end;
  const pointer=e=>local(e.x*innerWidth,e.y*innerHeight);
  window.NarrativeGesture?.on('pinch',e=>{const p=pointer(e);if(e.phase==='start')game.begin(p);else if(e.phase==='move')game.move(p);else game.end()});
  window.NarrativeGesture?.on('reset',()=>game.reset());
  document.getElementById('retry').onclick=()=>game.reset();render();
  </script>
</body>
```
In a full canvas game also implement keyboard control/accessible buttons, responsive letterboxing, and pointer cancellation. Normalize with the canvas bounding rectangle, not raw percent of canvas pixels. For DOM dwell, the platform Bootstrap hits only visible, enabled `[data-gesture-dwell]` elements. Canvas targets require your own hit-test.

## Quality and verification
Choose an appropriate template only if it serves the user's goal; otherwise generate custom markup. Define learning_goal, interactive_objects, gestures_used and assessment_feedback before implementation. Actions must change game state, give clear feedback and produce learning evidence, not merely show gesture buttons. Provide a visible alternative for every camera operation, a clear reset, mobile layout and no exposed answers. Use existing HTML Builder record_learning_plan, sandbox Chromium validation, automatic repair, and Artifact/version flows. Offline synthetic event testing proves only game bindings and Bridge mechanics; the browser camera, MediaPipe, Safari and performance require separate HTTPS/localhost device acceptance.
