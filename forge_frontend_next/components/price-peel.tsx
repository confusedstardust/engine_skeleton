"use client";

import { useEffect, useId, useRef, useState } from "react";

export function PriceFace({ value, annual }: { value: number; annual: boolean }) {
  return <div className={`price-paper-face${annual ? " is-annual" : ""}`}>
    <span className="price-paper-period">{annual ? "YEARLY" : "MONTHLY"}</span>
    <span className="price-paper-seal" aria-hidden="true">临场</span>
    <div className="pricing-price"><span>¥</span><strong>{value.toLocaleString("zh-CN", { maximumFractionDigits: 2, useGrouping: false })}</strong><small>{annual ? "/ 年" : "/ 月"}</small></div>
  </div>;
}

/** One continuous curl: face, paper back and shadow share the same timeline. */
export function PricePeel({ value }: { value: number }) {
  const id = useId().replace(/[^a-zA-Z0-9]/g, "");
  const svg = useRef<SVGSVGElement | null>(null);
  const [visible, setVisible] = useState(true);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setVisible(false);
      return;
    }
    let frame = 0;
    let start: number | null = null;
    const tick = (time: number) => {
      if (start === null) start = time;
      const t = Math.min(1, (time - start) / 1080);
      // Smooth acceleration and deceleration, without restarting at keyframes.
      const progress = t * t * (3 - 2 * t);
      const bottom = -92 + 392 * progress;
      const top = bottom + 92;
      const width = (20 + 40 * Math.sin(Math.PI * progress)) * Math.min(1, progress * 14);
      const clamp = (x: number) => Math.max(0, Math.min(300, x));
      svg.current?.querySelector("polygon")?.setAttribute("points", `${clamp(top)},0 300,0 300,92 ${clamp(bottom)},92`);
      const curl = `M ${top},0 L ${bottom},92 Q ${bottom + width * .65},101 ${bottom + width},88 L ${top + width},12 Q ${top + width * .8},-3 ${top},0 Z`;
      svg.current?.querySelectorAll(".paper-fold-shape").forEach((path) => path.setAttribute("d", curl));
      svg.current?.querySelector(".paper-crease")?.setAttribute("d", `M ${top},0 L ${bottom},92`);
      svg.current?.querySelector(".paper-shadow")?.setAttribute("opacity", String(.06 + .2 * Math.sin(Math.PI * progress)));
      svg.current?.querySelector("feGaussianBlur")?.setAttribute("stdDeviation", String(2 + 3 * Math.sin(Math.PI * progress)));
      svg.current?.querySelector("feOffset")?.setAttribute("dx", String(3 + 7 * Math.sin(Math.PI * progress)));
      if (t < 1) frame = requestAnimationFrame(tick);
      else setVisible(false);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);
  if (!visible) return null;
  return <div className="price-peel-layer" aria-hidden="true">
    <div className="price-paper-front" style={{ clipPath: `url(#${id}clip)` }}><PriceFace value={value} annual={false} /></div>
    <svg ref={svg} className="price-paper-curl" viewBox="0 0 300 92" preserveAspectRatio="none">
      <defs>
        <linearGradient id={`${id}back`} x1="0" y1="1" x2="1" y2="0"><stop stopColor="#d4c4a8" /><stop offset=".22" stopColor="#f4ead7" /><stop offset=".58" stopColor="#fffdf6" /><stop offset=".84" stopColor="#eadcc3" /><stop offset="1" stopColor="#b69a6d" /></linearGradient>
        <filter id={`${id}shadow`} x="-60%" y="-60%" width="240%" height="240%"><feGaussianBlur stdDeviation="2" /><feOffset dx="5" dy="3" /></filter>
        <clipPath id={`${id}clip`} clipPathUnits="objectBoundingBox"><polygon transform="scale(0.003333333333 0.010869565217)" points="0,0 300,0 300,92 0,92" /></clipPath>
      </defs>
      <path className="paper-fold-shape paper-shadow" fill="#523919" opacity="0" filter={`url(#${id}shadow)`} />
      <path className="paper-fold-shape" fill={`url(#${id}back)`} stroke="#cebea0" strokeWidth=".35" />
      <path className="paper-crease" fill="none" stroke="#fffdf2" strokeOpacity=".75" strokeWidth=".8" />
    </svg>
  </div>;
}
