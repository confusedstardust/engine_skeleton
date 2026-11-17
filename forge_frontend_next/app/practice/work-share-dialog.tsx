"use client";

import { useState } from "react";
import { Button } from "../../components/ui/button";
import { CloseButton } from "../../components/ui/close-button";
import { ModalBody, ModalFrame } from "../../components/ui/modal";
import { withBasePath } from "../base-path";
import type { SharedWork } from "../../lib/work-api";
import styles from "./practice.module.css";

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = reject;
    image.src = src;
  });
}

/** Use same-origin authenticated images so browser canvas is never CORS-tainted. */
async function makePoster(data: SharedWork) {
  const coverPath = withBasePath(`/api/forge/public/works/${data.work_id}/cover.png`);
  const qrPath = withBasePath(`/api/forge/works/${data.work_id}/share/qr.png`);
  const [cover, qr] = await Promise.all([loadImage(coverPath), loadImage(qrPath)]);
  const canvas = document.createElement("canvas");
  canvas.width = 1000;
  canvas.height = 1350;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("浏览器暂不支持制作分享海报");
  ctx.fillStyle = "#f7f6f0"; ctx.fillRect(0, 0, 1000, 1350);
  ctx.fillStyle = "#3c513f";
  ctx.font = "600 31px sans-serif";
  ctx.fillText("NarrativeOS  ·  互动学习作品", 58, 82);
  const ratio = Math.max(884 / cover.width, 510 / cover.height);
  const sw = 884 / ratio, sh = 510 / ratio;
  ctx.drawImage(cover, (cover.width - sw) / 2, (cover.height - sh) / 2, sw, sh, 58, 130, 884, 510);
  ctx.fillStyle = "#2e4233"; ctx.font = "bold 43px sans-serif";
  const title = data.title.slice(0, 66);
  let line = "", y = 730;
  for (const letter of title) {
    if (ctx.measureText(line + letter).width > 850) {
      ctx.fillText(line, 58, y); y += 60; line = letter;
    } else line += letter;
  }
  if (line) { ctx.fillText(line, 58, y); y += 60; }
  ctx.fillStyle = "#69796a"; ctx.font = "25px sans-serif";
  ctx.fillText("扫码打开这份互动学习作品", 58, Math.max(965, y + 50));
  ctx.drawImage(qr, 58, 1025, 240, 240);
  ctx.font = "24px sans-serif"; ctx.fillText("把知识变成可以探索的学习体验", 332, 1123);
  ctx.font = "18px sans-serif"; ctx.fillText("在 NarrativeOS 中创作与分享", 332, 1170);
  const url = canvas.toDataURL("image/png");
  const link = document.createElement("a");
  link.href = url; link.download = "NarrativeOS-互动学习作品.png";
  document.body.appendChild(link); link.click(); link.remove();
}

export default function WorkShareDialog({
  data, onClose,
}: {
  data: SharedWork;
  onClose: () => void;
}) {
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState(false);
  const cover = withBasePath(`/api/forge/public/works/${data.work_id}/cover.png`);
  const qr = withBasePath(`/api/forge/works/${data.work_id}/share/qr.png`);

  async function copy() {
    try {
      if (!navigator.clipboard?.writeText) throw new Error("clipboard unavailable");
      await navigator.clipboard.writeText(data.public_url);
      setFeedback("公开链接已复制");
    } catch {
      // HTTP development environments may not expose the secure Clipboard API.
      const field = document.createElement("textarea");
      field.value = data.public_url;
      field.style.position = "fixed"; field.style.opacity = "0";
      document.body.appendChild(field);
      field.select();
      const succeeded = document.execCommand("copy");
      field.remove();
      setFeedback(succeeded ? "公开链接已复制" : "浏览器无法自动复制，请手动选择链接");
    }
  }

  async function downloadPoster() {
    setBusy(true); setFeedback("");
    try { await makePoster(data); setFeedback("分享海报已下载"); }
    catch { setFeedback("海报生成失败，可以先复制链接分享"); }
    finally { setBusy(false); }
  }

  return <ModalFrame title="分享互动学习作品" onClose={onClose} busy={busy}>
    <div className={styles.publishOverlay}><ModalBody>
      <section className={styles.shareDialog}>
        <div className={styles.shareHeading}><h2>分享互动学习作品</h2>
          <CloseButton size="sm" onClick={onClose} aria-label="关闭分享弹窗" /></div>
        <img className={styles.shareCover} src={cover} alt={data.title + " 封面"} />
        <h3>{data.title}</h3>
        {data.summary && <p>{data.summary}</p>}
        <label htmlFor="public-work-link">公开作品链接</label>
        <div className={styles.shareLink}>
          <input id="public-work-link" readOnly value={data.public_url} onFocus={e => e.target.select()} />
          <Button size="sm" variant="outline" onClick={() => { void copy(); }}>复制</Button>
        </div>
        <div className={styles.shareActions}>
          <div className={styles.shareQr}><img src={qr} alt="公开作品二维码" /><span>扫码打开</span></div>
          <div className={styles.shareButtons}>
            <Button variant="primary" onClick={() => { void copy(); }}>复制公开链接</Button>
            <Button variant="outline" busy={busy} onClick={() => { void downloadPoster(); }}>下载分享海报</Button>
          </div>
        </div>
        {feedback && <p role="status" className={styles.shareFeedback}>{feedback}</p>}
      </section>
    </ModalBody></div>
  </ModalFrame>;
}
