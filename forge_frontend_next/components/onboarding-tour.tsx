"use client";

import { CSSProperties, useCallback, useEffect, useRef, useState } from "react";

const TOUR_STORAGE_KEY = "narrativeos:onboarding:v1";

type TourStep = {
  target: string;
  eyebrow: string;
  title: string;
  body: string;
};

type CardPosition = {
  top: number;
  left: number;
  placement: "top" | "right" | "bottom" | "left";
};

const steps: TourStep[] = [
  {
    target: "invite",
    eyebrow: "先解锁创作权限",
    title: "输入你的邀请码",
    body: "从右上角进入邀请码页面，解锁临场创作之旅。移动端请先展开菜单。"
  },
  {
    target: "topic",
    eyebrow: "告诉 AI 这堂课讲什么",
    title: "写下课堂主题",
    body: "用一句话写下想做的主题，例如“《关雎》中的爱情与礼教”。"
  },
  {
    target: "material",
    eyebrow: "给 AI 一点教学依据",
    title: "加入教学文本",
    body: "粘贴原文、知识点，或直接描述你希望这堂课如何设计。"
  },
  {
    target: "mode",
    eyebrow: "选择你的参与方式",
    title: "决定生成模式",
    body: "Auto 会一键生成可玩的初版；Advance 可逐步审阅大纲、场景和素材。"
  },
  {
    target: "voice",
    eyebrow: "让角色真正开口",
    title: "开启角色配音",
    body: "开启后，游戏角色会拥有 AI 配音，让课堂叙事更有临场感。"
  },
  {
    target: "image",
    eyebrow: "让叙事拥有画面",
    title: "保留图片素材",
    body: "建议保持开启。你还可以在旁边选择豆包或千问生图模型。"
  }
];

const CARD_WIDTH = 390;
const CARD_HEIGHT = 276;
const VIEWPORT_MARGIN = 20;
const TARGET_GAP = 22;

function visibleTarget(name: string): HTMLElement | null {
  const candidates = Array.from(document.querySelectorAll<HTMLElement>(`[data-tour="${name}"]`));
  return candidates.find((element) => {
    const rect = element.getBoundingClientRect();
    const style = window.getComputedStyle(element);
    return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
  }) || null;
}

function cardPosition(rect: DOMRect): CardPosition {
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  const maxLeft = Math.max(VIEWPORT_MARGIN, viewportWidth - CARD_WIDTH - VIEWPORT_MARGIN);
  const maxTop = Math.max(VIEWPORT_MARGIN, viewportHeight - CARD_HEIGHT - VIEWPORT_MARGIN);
  const centeredLeft = Math.min(maxLeft, Math.max(VIEWPORT_MARGIN, rect.left + rect.width / 2 - CARD_WIDTH / 2));

  if (rect.bottom + TARGET_GAP + CARD_HEIGHT <= viewportHeight - VIEWPORT_MARGIN) {
    return {
      top: rect.bottom + TARGET_GAP,
      left: centeredLeft,
      placement: "bottom"
    };
  }
  if (rect.top - TARGET_GAP - CARD_HEIGHT >= VIEWPORT_MARGIN) {
    return {
      top: rect.top - TARGET_GAP - CARD_HEIGHT,
      left: centeredLeft,
      placement: "top"
    };
  }
  if (rect.right + TARGET_GAP + CARD_WIDTH <= viewportWidth - VIEWPORT_MARGIN) {
    return {
      top: Math.min(maxTop, Math.max(VIEWPORT_MARGIN, rect.top + rect.height / 2 - CARD_HEIGHT / 2)),
      left: rect.right + TARGET_GAP,
      placement: "right"
    };
  }
  return {
    top: Math.min(maxTop, Math.max(VIEWPORT_MARGIN, rect.top + rect.height / 2 - CARD_HEIGHT / 2)),
    left: Math.max(VIEWPORT_MARGIN, rect.left - TARGET_GAP - CARD_WIDTH),
    placement: "left"
  };
}

export function OnboardingTour() {
  const [ready, setReady] = useState(false);
  const [open, setOpen] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  const [position, setPosition] = useState<CardPosition | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const step = steps[stepIndex];

  const updateLayout = useCallback(() => {
    if (!open) return;
    const target = visibleTarget(steps[stepIndex].target);
    if (!target) {
      setPosition(null);
      return;
    }
    const rect = target.getBoundingClientRect();
    setPosition(cardPosition(rect));
  }, [open, stepIndex]);

  useEffect(() => {
    setReady(true);
    try {
      if (window.localStorage.getItem(TOUR_STORAGE_KEY) !== "complete") {
        setOpen(true);
      }
    } catch {
      setOpen(true);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    const target = visibleTarget(step.target);
    const focusContext = target?.closest<HTMLElement>(".top-nav, .form-panel");
    target?.classList.add("onboarding-focused");
    focusContext?.classList.add("onboarding-focus-context");
    target?.scrollIntoView({ behavior: "auto", block: "center", inline: "nearest" });

    const firstFrame = window.requestAnimationFrame(updateLayout);
    const settledTimer = window.setTimeout(updateLayout, 0);
    const handleViewportChange = () => updateLayout();
    window.addEventListener("resize", handleViewportChange);
    cardRef.current?.focus({ preventScroll: true });

    return () => {
      window.cancelAnimationFrame(firstFrame);
      window.clearTimeout(settledTimer);
      window.removeEventListener("resize", handleViewportChange);
      target?.classList.remove("onboarding-focused");
      focusContext?.classList.remove("onboarding-focus-context");
    };
  }, [open, step, updateLayout]);

  const closeTour = useCallback(() => {
    try {
      window.localStorage.setItem(TOUR_STORAGE_KEY, "complete");
    } catch {
      // The tour can still be dismissed when storage is unavailable.
    }
    setOpen(false);
    setPosition(null);
  }, []);

  useEffect(() => {
    if (!open) return;
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") closeTour();
      if (event.key === "ArrowLeft" && stepIndex > 0) setStepIndex((current) => current - 1);
      if (event.key === "ArrowRight") {
        if (stepIndex === steps.length - 1) closeTour();
        else setStepIndex((current) => current + 1);
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [closeTour, open, stepIndex]);

  function restartTour() {
    setStepIndex(0);
    setOpen(true);
  }

  function nextStep() {
    if (stepIndex === steps.length - 1) closeTour();
    else setStepIndex((current) => current + 1);
  }

  if (!ready) return null;

  const cardStyle = position
    ? ({ top: position.top, left: position.left } as CSSProperties)
    : undefined;

  return (
    <>
      {open && (
        <>
          <div className="onboarding-veil" aria-hidden="true" />
          <div className="onboarding-layer" aria-live="polite">
            <div
            ref={cardRef}
            className={`onboarding-card onboarding-${position?.placement || "center"}`}
            style={cardStyle}
            role="dialog"
            aria-modal="true"
            aria-labelledby="onboarding-title"
            aria-describedby="onboarding-description"
            tabIndex={-1}
            >
            <div className="onboarding-mark" aria-hidden="true">✦</div>
            <div className="onboarding-progress" aria-hidden="true">
              <span style={{ width: `${((stepIndex + 1) / steps.length) * 100}%` }} />
            </div>
            <span className="onboarding-eyebrow">{step.eyebrow}</span>
            <h2 id="onboarding-title">{step.title}</h2>
            <p id="onboarding-description">{step.body}</p>
            <div className="onboarding-actions">
              <button className="onboarding-skip" type="button" onClick={closeTour}>跳过引导</button>
              <span>{stepIndex + 1} / {steps.length}</span>
              {stepIndex > 0 && <button className="onboarding-prev" type="button" onClick={() => setStepIndex((current) => current - 1)}>上一步</button>}
              <button className="onboarding-next" type="button" onClick={nextStep}>
                {stepIndex === steps.length - 1 ? "开始创作" : "下一步"}
              </button>
            </div>
            </div>
          </div>
        </>
      )}

      {!open && (
        <button className="onboarding-restart" type="button" onClick={restartTour} aria-label="重新打开新手引导">
          <span aria-hidden="true">?</span>
          新手引导
        </button>
      )}
    </>
  );
}
