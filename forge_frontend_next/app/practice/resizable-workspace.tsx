"use client";

import { type CSSProperties, type PointerEvent, type ReactNode, useEffect, useRef, useState } from "react";
import styles from "./practice.module.css";

const HANDLE = 10;
const MIN_NAV = 180;
const MAX_NAV = 284;
const MIN_CHAT = 310;
const MIN_PREVIEW = 370;
const DEFAULT_NAV = 216;
const DEFAULT_CHAT_SHARE = 0.36;

function bounded(value: number, low: number, high: number) {
  return Math.max(low, Math.min(high, value));
}

type GripKind = "navigation" | "preview";

type DragHandleProps = {
  kind: GripKind;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
  onDragMove: (clientX: number) => void;
  disabled?: boolean;
};

function DragHandle({ kind, value, min, max, onChange, onDragMove, disabled = false }: DragHandleProps) {
  const dragging = useRef(false);

  function start(event: PointerEvent<HTMLDivElement>) {
    if (disabled || event.button !== 0) return;
    dragging.current = true;
    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
    document.body.style.userSelect = "none";
  }
  function end(event: PointerEvent<HTMLDivElement>) {
    if (!dragging.current) return;
    dragging.current = false;
    document.body.style.userSelect = "";
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }
  const preview = kind === "preview";
  return <div
    className={`${styles.resizeHandle} ${preview ? styles.resizePreview : styles.resizeNavigation}`}
    role="separator" tabIndex={disabled ? -1 : 0} aria-orientation="vertical"
    aria-label={preview ? "拖动调整对话与作品预览的宽度" : "拖动调整左侧导航宽度"}
    aria-valuemin={min} aria-valuemax={max} aria-valuenow={Math.round(value)}
    aria-valuetext={preview ? `对话区域占可用空间约 ${Math.round(value)}%` : `导航宽度 ${Math.round(value)} 像素`}
    onPointerDown={start}
    onPointerMove={event => { if (dragging.current) onDragMove(event.clientX); }}
    onPointerUp={end} onPointerCancel={end}
    onLostPointerCapture={() => { dragging.current = false; document.body.style.userSelect = ""; }}
    onKeyDown={event => {
      const increment = event.shiftKey ? 32 : 12;
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault();
        onChange(bounded(value + (event.key === "ArrowRight" ? increment : -increment), min, max));
      } else if (event.key === "Home" || event.key === "End") {
        event.preventDefault();
        onChange(event.key === "Home" ? min : max);
      }
    }}>
    <span aria-hidden="true" className={styles.resizeGrip}><i/><i/><i/></span>
  </div>;
}

/**
 * Three independent card surfaces. The work opens with a generous 64% share;
 * explicit user resizing wins thereafter and persists for that SSO user.
 * Mobile reuses the existing overlay inspector instead of forcing tiny columns.
 */
export default function ResizableWorkspace({
  navigation, chat, inspector, userId,
}: {
  navigation: ReactNode;
  chat: ReactNode;
  inspector?: ReactNode;
  userId: string | null;
}) {
  const [navWidth, setNavWidth] = useState(DEFAULT_NAV);
  const [chatShare, setChatShare] = useState(DEFAULT_CHAT_SHARE);
  const [loaded, setLoaded] = useState(false);
  const layout = useRef<HTMLDivElement>(null);
  const hasInspector = Boolean(inspector);

  useEffect(() => {
    if (!userId) { setLoaded(false); return; }
    try {
      const raw = localStorage.getItem(`narrativeos:practice:layout:v1:${userId}`);
      const data = raw ? JSON.parse(raw) as { nav?: number; chat?: number } : null;
      if (data && Number.isFinite(data.nav)) setNavWidth(bounded(data.nav!, MIN_NAV, MAX_NAV));
      if (data && Number.isFinite(data.chat)) setChatShare(bounded(data.chat!, 0.24, 0.68));
    } catch { /* Storage may be disabled. */ }
    setLoaded(true);
  }, [userId]);

  useEffect(() => {
    if (!loaded || !userId) return;
    try {
      localStorage.setItem(`narrativeos:practice:layout:v1:${userId}`,
        JSON.stringify({ nav: navWidth, chat: chatShare }));
    } catch { /* Resize works even without persistent preferences. */ }
  }, [navWidth, chatShare, userId, loaded]);

  function movePreview(clientX: number) {
    const bounds = layout.current?.getBoundingClientRect();
    if (!bounds || !hasInspector) return;
    const available = bounds.width - navWidth - HANDLE * 2;
    if (available < MIN_CHAT + MIN_PREVIEW) return;
    const chatWidth = bounded(clientX - bounds.left - navWidth - HANDLE,
      MIN_CHAT, available - MIN_PREVIEW);
    setChatShare(bounded(chatWidth / available, 0.20, 0.75));
  }

  const css = {
    "--studio-nav": `${navWidth}px`,
    "--studio-chat": `${chatShare}fr`,
    "--studio-preview": `${1 - chatShare}fr`,
  } as CSSProperties;

  return <div ref={layout} style={css}
    className={`${styles.layout} ${hasInspector ? styles.layoutWithInspector : ""}`}>
    {navigation}
    <DragHandle kind="navigation" value={navWidth} min={MIN_NAV} max={MAX_NAV}
      onChange={setNavWidth} onDragMove={x => {
        const bounds = layout.current?.getBoundingClientRect();
        if (bounds) setNavWidth(bounded(x - bounds.left, MIN_NAV, MAX_NAV));
      }} />
    {chat}
    {hasInspector && <>
      <DragHandle kind="preview" value={chatShare * 100} min={24} max={68}
        onChange={percent => setChatShare(percent / 100)}
        onDragMove={movePreview} />
      {inspector}
    </>}
  </div>;
}
