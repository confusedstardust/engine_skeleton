import {withBasePath} from "../../app/base-path";
import {GestureAdapter,type GestureFrame} from "./adapter";
import type {GestureEvent} from "./protocol";
type Hands={startCamera:()=>Promise<void>;stop:()=>void;tracker:{onEnded:(()=>void)|null}};
type Module={createHands:(opts:Record<string,unknown>)=>Hands};
let sdk:Module|null=null;
let loading:Promise<boolean>|null=null;
let activeStop:(()=>void)|null=null;
/** Called from mount, never after the camera button click. */
export function preloadGestureSDK():Promise<boolean>{
  if(sdk)return Promise.resolve(true);
  if(!loading){
    const url=withBasePath("/gesture-sdk/v1/hand-gesture-kit.esm.js");
    loading=import(/* webpackIgnore: true */ url).then((mod:unknown)=>{
      if(!mod || typeof (mod as Module).createHands!=="function")throw Error("Invalid hand gesture SDK");
      sdk=mod as Module;return true;
    }).catch(()=>{loading=null;return false;});
  }
  return loading;
}
export function createGestureRuntime(
  video:HTMLVideoElement,emit:(event:GestureEvent)=>void,onEnded:()=>void
){
  let hands:Hands|null=null,closed=false;
  const adapter=new GestureAdapter(emit);
  const stop=()=>{
    if(closed)return;
    closed=true;adapter.release();hands?.stop();hands=null;video.srcObject=null;
    if(activeStop===stop)activeStop=null;
  };
  function start():Promise<void>{
    if(!sdk)throw Error("SDK_NOT_READY");
    if(activeStop&&activeStop!==stop)activeStop();
    activeStop=stop;
    hands=sdk.createHands({
      video,assetBase:withBasePath("/gesture-sdk/v1/"),numHands:1,
      camera:{audio:false,video:{facingMode:"user",width:{ideal:640},height:{ideal:480},frameRate:{ideal:30}}},
      config:{pose:{experimental:false}},
      onFrame:(frame:GestureFrame)=>{if(!closed)adapter.consume(frame)},
    });
    hands.tracker.onEnded=()=>{stop();onEnded();};
    // SDK calls getUserMedia synchronously, before its first await.
    return hands.startCamera().then(()=>{if(closed)hands?.stop();}).catch(error=>{stop();throw error;});
  }
  return {start,stop};
}
