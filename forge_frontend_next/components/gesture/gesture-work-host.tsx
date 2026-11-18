"use client";
import {useCallback,useEffect,useRef,useState} from "react";
import {buildPreviewHTML} from "../../lib/gesture-bridge/build-preview-html";
import {supportsGestureBridge} from "../../lib/gesture-bridge/capability";
import {createGestureRuntime,preloadGestureSDK} from "../../lib/gesture-bridge/runtime";
import {validControlMessage,type GestureEvent} from "../../lib/gesture-bridge/protocol";
import {Button} from "../../components/ui/button";
import styles from "./gesture-work-host.module.css";

type Bridge={port:MessagePort;sessionId:string;seq:number;recvSeq:number;ready:boolean;window:Window};
type Runtime=ReturnType<typeof createGestureRuntime>;
export default function GestureWorkHost({html,label="互动作品",compact=false,fullHeight=false,disclaimer=false}:{
  html:string;label?:string;compact?:boolean;fullHeight?:boolean;disclaimer?:boolean;
}){
  const capable=supportsGestureBridge(html);
  const root=useRef<HTMLElement>(null),frame=useRef<HTMLIFrameElement>(null),video=useRef<HTMLVideoElement>(null);
  const bridge=useRef<Bridge|null>(null),runtime=useRef<Runtime|null>(null);
  const [source,setSource]=useState(""),[sdkReady,setSdkReady]=useState(false);
  const [bridgeReady,setBridgeReady]=useState(false);
  const [state,setState]=useState<"off"|"starting"|"running"|"stopping"|"error">("off");
  const [notice,setNotice]=useState(""),[cursor,setCursor]=useState<{x:number;y:number}|null>(null);

  const send=useCallback((event:GestureEvent)=>{
    const b=bridge.current;
    if(!b?.ready)return;
    b.port.postMessage({channel:"nar-gesture",v:1,sessionId:b.sessionId,seq:++b.seq,type:"EVENT",event});
  },[]);
  const stop=useCallback(()=>{
    const old=runtime.current;runtime.current=null;
    old?.stop();setCursor(null);setState("off");send({kind:"status",state:"off"});
  },[send]);
  const disconnect=useCallback(()=>{
    const b=bridge.current;bridge.current=null;setBridgeReady(false);
    if(b){b.ready=false;b.port.onmessage=null;b.port.close();}
  },[]);
  const connect=useCallback(()=>{
    stop();disconnect();
    const child=frame.current?.contentWindow;
    if(!child||!capable||!source)return;
    const id=Array.from(crypto.getRandomValues(new Uint8Array(24)),n=>n.toString(16).padStart(2,"0")).join("");
    const channel=new MessageChannel();
    const b:Bridge={port:channel.port1,sessionId:id,seq:0,recvSeq:-1,ready:false,window:child};
    bridge.current=b;
    b.port.onmessage=message=>{
      if(bridge.current!==b||frame.current?.contentWindow!==b.window)return;
      if(!validControlMessage(message.data,b.sessionId,b.recvSeq))return;
      b.recvSeq=message.data.seq;
      if(message.data.type==="READY"&&!b.ready){
        b.ready=true;setBridgeReady(true);send({kind:"status",state:"off"});
      }else if(message.data.type==="DISPOSED"){stop();disconnect();}
    };
    b.port.start();
    // Transfer a capability-free port only to this exact opaque-origin iframe.
    child.postMessage({channel:"nar-gesture",v:1,type:"NAR_GESTURE_CONNECT",sessionId:id},"*",[channel.port2]);
  },[capable,source,stop,disconnect,send]);
  useEffect(()=>{
    setSource(buildPreviewHTML(html,window.location.origin));
    setNotice("");
  },[html]);
  useEffect(()=>{
    if(!capable)return;
    let mounted=true;
    void preloadGestureSDK().then(ok=>{if(mounted){setSdkReady(ok);if(!ok)setNotice("手势资源未就绪，可继续使用鼠标或触屏。");}});
    return ()=>{mounted=false;};
  },[capable]);
  useEffect(()=>{
    const hidden=()=>{if(document.hidden){stop();disconnect();}else if(capable)connect();};
    const leaving=()=>{stop();disconnect();};
    document.addEventListener("visibilitychange",hidden);
    window.addEventListener("pagehide",leaving);
    return ()=>{document.removeEventListener("visibilitychange",hidden);window.removeEventListener("pagehide",leaving);stop();disconnect();};
  },[stop,disconnect,connect,capable]);

  const toggleCamera=()=>{
    if(runtime.current){stop();setNotice("摄像头已关闭。");return;}
    if(!capable||!sdkReady||!bridge.current?.ready||!video.current)return;
    if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia){
      setNotice("摄像头需要 HTTPS 或 localhost；当前仍可使用键盘、鼠标和触屏。");return;
    }
    const instance=createGestureRuntime(video.current,event=>{
      if(event.kind==="pointer")setCursor(event.visible?{x:event.x!,y:event.y!}:null);
      send(event);
    },()=>{
      if(runtime.current===instance){runtime.current=null;setState("error");setCursor(null);
        send({kind:"status",state:"error",code:"DEVICE_ENDED"});setNotice("摄像头已断开，请重新开启。");}
    },()=>{
      if(runtime.current===instance){runtime.current=null;setState("off");setCursor(null);
        send({kind:"status",state:"off"});
        setNotice("另一个作品已开启手势，当前摄像头已自动关闭。");}
    });
    runtime.current=instance;
    setState("starting");setNotice("正在开启摄像头并加载手势模型…");
    send({kind:"status",state:"starting"});
    // Important: startCamera invokes getUserMedia directly in this click handler.
    let started:Promise<void>;
    try{started=instance.start();}catch(error){started=Promise.reject(error);}
    void started.then(()=>{
      if(runtime.current!==instance)return;
      setState("running");setNotice("手势在本机识别，不上传视频或关键点。");
      send({kind:"status",state:"running"});
    }).catch((error:unknown)=>{
      if(runtime.current!==instance)return;
      runtime.current=null;instance.stop();setCursor(null);setState("error");
      const name=error instanceof Error?error.name:"CameraError";
      setNotice(name==="NotAllowedError"?"未获得摄像头权限，可继续使用鼠标或触屏。":
        name==="NotFoundError"?"没有检测到摄像头，可继续使用鼠标或触屏。":
        "无法开启手势（"+name+"），可继续使用鼠标或触屏。");
      send({kind:"status",state:"error",code:name.slice(0,64)});
    });
  };
  const fullscreen=()=>{void root.current?.requestFullscreen().catch(()=>setNotice("无法进入全屏。"));};
  return <section ref={root} className={[styles.host,compact?styles.compact:"",fullHeight?styles.fullHeight:""].join(" ")} aria-label={label}>
    <header className={styles.toolbar}>
      <strong>{label}</strong>
      <div className={styles.buttons}>
        {capable&&<Button size="sm" onClick={toggleCamera}
          disabled={!sdkReady||!bridgeReady||state==="starting"}>
          {state==="running"?"关闭手势":"开启手势"}
        </Button>}
        <Button size="sm" onClick={fullscreen}>全屏展示</Button>
      </div>
    </header>
    <div className={styles.stage}>
      <iframe ref={frame} title={label} sandbox="allow-scripts" allow="fullscreen" allowFullScreen
        referrerPolicy="no-referrer" srcDoc={source} onLoad={connect}/>
      {cursor&&state==="running"&&<div className={styles.pointer} aria-hidden="true"
        style={{left:(cursor.x*100)+"%",top:(cursor.y*100)+"%"}}/>}
      <video ref={video} autoPlay muted playsInline className={state==="running"?styles.camera:styles.cameraHidden} aria-hidden="true"/>
    </div>
    {capable&&<p role="status" className={styles.notice}>
      {notice||(!sdkReady?"正在准备手势组件…":!bridgeReady?"正在连接作品…":"点击开启手势，浏览器会请求摄像头权限。")}
    </p>}
    {disclaimer&&<p className={styles.disclaimer}>基础浏览器检查不等于课堂教学准确性或真机手势识别验收，请在使用前核对。</p>}
  </section>;
}
