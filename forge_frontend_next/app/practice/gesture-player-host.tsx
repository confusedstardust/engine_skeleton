"use client";
import { useEffect, useRef, useState, type RefObject } from "react";
import { withBasePath } from "../../app/base-path";
import { GestureBridge } from "../../lib/gesture/gesture-bridge";
import { GestureRuntime } from "../../lib/gesture/gesture-runtime";
import type { GestureBindings, GestureManifest } from "../../lib/gesture/gesture-types";
import styles from "./gesture-player-host.module.css";

let manifestPromise: Promise<GestureManifest> | null = null;
function getManifest(): Promise<GestureManifest> {
  if (!manifestPromise) {
    manifestPromise = fetch(withBasePath("/gesture/manifest.v0.2.json"),{cache:"force-cache"})
      .then(async r => { if (!r.ok) throw new Error("手势能力清单加载失败"); return await r.json() as GestureManifest; })
      .catch(error => { manifestPromise = null; throw error; });
  }
  return manifestPromise;
}

/** Shared trusted host for chat preview and saved/public work pages. */
export default function GesturePlayerHost({
  src, srcDoc, title, frameRef
}: {src?:string;srcDoc?:string;title:string;frameRef?:RefObject<HTMLIFrameElement | null>}) {
  const iframe = useRef<HTMLIFrameElement>(null);
  const bridge = useRef<GestureBridge | null>(null);
  const runtime = useRef<GestureRuntime | null>(null);
  const [bindings,setBindings] = useState<GestureBindings | null>(null);
  const [manifest,setManifest] = useState<GestureManifest | null>(null);
  const [active,setActive] = useState(false);
  const [starting,setStarting] = useState(false);
  const [error,setError] = useState("");

  useEffect(() => {
    let disposed = false;
    // No manifest fetch, MediaPipe loading, or camera request for ordinary HTML.
    const onHello = (event: MessageEvent) => {
      if (event.source !== iframe.current?.contentWindow || event.data?.protocol !== "nar.gesture/0.2" ||
          event.data?.type !== "hello") return;
      void getManifest().then(definitions => {
        if (disposed || event.source !== iframe.current?.contentWindow) return;
        if (bridge.current) return;
        const instance = new GestureBridge(iframe.current!,definitions,
          available => { if (!disposed) { setBindings(available); setManifest(definitions); setError(""); } },
          hasTarget => runtime.current?.setHoverTarget(hasTarget));
        bridge.current = instance;
        instance.handleHello(event);
      }).catch(err => { if (!disposed) setError(err instanceof Error ? err.message : "手势能力无法加载"); });
    };
    window.addEventListener("message",onHello);
    return () => {
      disposed = true; window.removeEventListener("message",onHello);
      runtime.current?.dispose(); runtime.current = null;
      bridge.current?.dispose(); bridge.current = null;
      setBindings(null); setManifest(null); setActive(false);
    };
  }, [src,srcDoc]);

  useEffect(() => {
    const onHide = () => {
      if (document.hidden) {
        runtime.current?.stop();
        setActive(false);
      }
    };
    document.addEventListener("visibilitychange",onHide);
    return () => document.removeEventListener("visibilitychange",onHide);
  }, []);

  const stop = () => {
    runtime.current?.stop(); setActive(false); setStarting(false);
  };
  const start = async () => {
    if (starting || active || !manifest || !bindings || !bridge.current) return;
    setStarting(true); setError("");
    const instance = new GestureRuntime(bindings,manifest,(action,event) => bridge.current?.send(action,event));
    runtime.current?.dispose(); runtime.current = instance;
    try { await instance.start(); if (runtime.current === instance) setActive(true); }
    catch (err) { setError(err instanceof Error ? err.message : "摄像头不可用；可继续使用鼠标或触屏"); instance.dispose(); }
    finally { setStarting(false); }
  };

  return <>
    <iframe ref={node => { iframe.current = node; if (frameRef) frameRef.current = node; }} title={title} sandbox="allow-scripts"
      allow="fullscreen" allowFullScreen referrerPolicy="no-referrer"
      src={src} srcDoc={srcDoc} />
    {bindings && <div className={styles.controls}>
      <button type="button" onClick={active ? stop : () => { void start(); }} disabled={starting}>
        {starting ? "正在启动…" : active ? "关闭手势控制" : "开启手势控制"}
      </button>
      <span>{active ? "摄像头正在本地识别手势" : "手势模式可选；普通操作始终可用"}</span>
    </div>}
    {error && <p className={styles.error} role="alert">{error}。可继续使用鼠标或触屏。</p>}
  </>;
}
