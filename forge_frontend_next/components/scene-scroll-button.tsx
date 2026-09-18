"use client";

import { useEffect, useState } from "react";

export function scrollDirection(scrollTop: number, maxScroll: number): "top" | "bottom" {
  if (scrollTop <= 24) return "bottom";
  if (maxScroll - scrollTop <= 24) return "top";
  return scrollTop >= maxScroll / 2 ? "top" : "bottom";
}

export function scrollButtonRight(viewportWidth: number, inspectorLeft?: number): number {
  return viewportWidth > 1180 && inspectorLeft !== undefined
    ? Math.max(24, viewportWidth - inspectorLeft - 64)
    : 24;
}

export function SceneScrollButton() {
  const [target, setTarget] = useState<"top" | "bottom">("bottom");
  const [canScroll, setCanScroll] = useState(false);
  const [right, setRight] = useState(24);

  useEffect(() => {
    let frame: number | null = null;
    const update = () => {
      const root = document.scrollingElement || document.documentElement;
      const max = Math.max(0, root.scrollHeight - window.innerHeight);
      setCanScroll(max > 24);
      setTarget(scrollDirection(root.scrollTop, max));
      const inspector = document.querySelector(".laper-scene-shell .laper-inspector");
      setRight(scrollButtonRight(window.innerWidth, inspector?.getBoundingClientRect().left));
    };
    const schedule = () => {
      if (frame !== null) return;
      frame = window.requestAnimationFrame(() => { frame = null; update(); });
    };
    update();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    const observer = new ResizeObserver(schedule);
    observer.observe(document.body);
    observer.observe(document.documentElement);
    return () => {
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      observer.disconnect();
      if (frame !== null) window.cancelAnimationFrame(frame);
    };
  }, []);

  if (!canScroll) return null;
  const label = target === "bottom" ? "滚动到页面底部" : "返回页面顶部";
  return (
    <button className="scene-scroll-button" style={{ right: `max(${right}px, env(safe-area-inset-right))` }} type="button" aria-label={label} title={label}
      onClick={() => {
        const root = document.scrollingElement || document.documentElement;
        window.scrollTo({ top: target === "top" ? 0 : Math.max(0, root.scrollHeight - window.innerHeight),
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
      }}>
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d={target === "bottom" ? "M12 5v14M6 13l6 6 6-6" : "M12 19V5M6 11l6-6 6 6"}
          stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  );
}
