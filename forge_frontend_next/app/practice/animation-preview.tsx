"use client";
import GesturePlayerHost from "./gesture-player-host";
import styles from "./practice.module.css";

const CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'";

export default function AnimationPreview({ html, label = "动画成品预览", compact = false }: { html: string; label?: string; compact?: boolean }) {
  return <section className={`${styles.preview} ${compact ? styles.previewCompact : ""}`} aria-label={label}>
    <header><strong>{label}</strong><div className={styles.actions}>

    </div></header>
    <GesturePlayerHost title="教学动画" srcDoc={`<!doctype html><meta http-equiv="Content-Security-Policy" content="${CSP}"><meta name="referrer" content="no-referrer">${html}`} />
    <p>构建与基础浏览器检查已通过；画面、交互效果和教学准确性请在课堂使用前核对。</p>
  </section>;
}
