"use client";
import { useRef } from "react";
import { withBasePath } from "../base-path";
import { Button } from "../../components/ui/button";
import styles from "./practice.module.css";

const CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'";

export default function AnimationPreview({ html, artifactId }: { html: string; artifactId: string }) {
  const frame = useRef<HTMLIFrameElement>(null);
  return <section className={styles.preview} aria-label="动画成品预览">
    <header><strong>交互演示</strong><Button size="sm" onClick={() => { void frame.current?.requestFullscreen().catch(() => undefined); }}>全屏展示</Button></header>
    <iframe ref={frame} title="教学动画" sandbox="allow-scripts" allow="fullscreen" allowFullScreen referrerPolicy="no-referrer" srcDoc={`<!doctype html><meta http-equiv="Content-Security-Policy" content="${CSP}"><meta name="referrer" content="no-referrer">${html}`} />
    <details><summary>查看自动检查截图</summary><img alt="桌面检查截图" src={withBasePath(`/api/forge/nar-agent/artifacts/${artifactId}/preview.png`)} /><img alt="手机检查截图" src={withBasePath(`/api/forge/nar-agent/artifacts/${artifactId}/mobile.png`)} /></details>
    <p>构建与基础浏览器检查已通过；画面、交互效果和教学准确性请在课堂使用前核对。</p>
  </section>;
}
