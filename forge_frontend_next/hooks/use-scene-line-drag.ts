"use client";
import { useEffect, useRef, useState, type RefObject } from "react";

/** Shared workbench sorting: pointer capture, insertion hints and edge scrolling. */
export function useSceneLineDrag({ disabled, containerRef, selector, indexAttribute, canDrag, onReorder }: {
  disabled: boolean;
  containerRef: RefObject<HTMLElement | null>;
  selector: string;
  indexAttribute: string;
  canDrag?: (index: number) => boolean;
  onReorder: (from: number, to: number) => void;
}) {
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [dropHint, setDropHint] = useState<{ index: number; placement: "before" | "after" } | null>(null);
  const pointerDragIdRef = useRef<number | null>(null);
  const sourceIndexRef = useRef<number | null>(null);
  const dropHintRef = useRef<{ index: number; placement: "before" | "after" } | null>(null);
  const pointerYRef = useRef<number | null>(null);
  const scrollFrameRef = useRef<number | null>(null);
  function stopLineAutoScroll() {
    pointerDragIdRef.current = null;
    sourceIndexRef.current = null;
    dropHintRef.current = null;
    pointerYRef.current = null;
    setDropHint(null);
    if (scrollFrameRef.current !== null) {
      window.cancelAnimationFrame(scrollFrameRef.current);
      scrollFrameRef.current = null;
    }
  }

  function updateLineAutoScroll(pointerY: number) {
    pointerYRef.current = pointerY;
    if (scrollFrameRef.current !== null) return;
    const scroll = () => {
      const y = pointerYRef.current;
      if (y === null) {
        scrollFrameRef.current = null;
        return;
      }
      const height = window.visualViewport?.height || window.innerHeight;
      const top = window.visualViewport?.offsetTop || 0;
      const edge = Math.min(179, Math.round(height * 0.192));
      const topDistance = y - top;
      const bottomDistance = top + height - y;
      const delta = topDistance < edge
        ? -Math.max(6, Math.round(((edge - topDistance) / edge) * 27))
        : bottomDistance < edge
          ? Math.max(6, Math.round(((edge - bottomDistance) / edge) * 27))
          : 0;
      if (!delta) {
        scrollFrameRef.current = null;
        return;
      }
      window.scrollBy({ top: delta, behavior: "auto" });
      scrollFrameRef.current = window.requestAnimationFrame(scroll);
    };
    scrollFrameRef.current = window.requestAnimationFrame(scroll);
  }

  function startLineDrag(index: number, pointerId: number, pointerY: number) {
    if (disabled) return;
    if (canDrag && !canDrag(index)) return;
    pointerDragIdRef.current = pointerId;
    sourceIndexRef.current = index;
    setDragIndex(index);
    updateLineAutoScroll(pointerY);
  }

  function moveLineDrag(pointerId: number, pointerX: number, pointerY: number) {
    if (pointerDragIdRef.current !== pointerId) return;
    updateLineAutoScroll(pointerY);
    const card = document.elementFromPoint(pointerX, pointerY)?.closest<HTMLElement>(selector);
    if (!card || !containerRef.current?.contains(card)) return;
    const targetIndex = Number(card.getAttribute(indexAttribute));
    if (sourceIndexRef.current === null || Number.isNaN(targetIndex) || targetIndex === sourceIndexRef.current) return;
    const bounds = card?.getBoundingClientRect();
    const nextHint = { index: targetIndex, placement: bounds && pointerY > bounds.top + bounds.height / 2 ? "after" : "before" } as const;
    if (dropHintRef.current?.index !== nextHint.index || dropHintRef.current.placement !== nextHint.placement) {
      dropHintRef.current = nextHint;
      setDropHint(nextHint);
    }
  }

  function finishLineDrag(pointerId: number) {
    if (pointerDragIdRef.current !== pointerId) return;
    const from = sourceIndexRef.current;
    const target = dropHintRef.current;
    if (from !== null && target && from !== target.index) {
      let insertionIndex = target.index + (target.placement === "after" ? 1 : 0);
      if (from < insertionIndex) insertionIndex -= 1;
      onReorder(from, insertionIndex);
    }
    setDragIndex(null);
    stopLineAutoScroll();
  }

  useEffect(() => () => stopLineAutoScroll(), []);

  return { dragIndex, setDragIndex, dropHint, startLineDrag, moveLineDrag, finishLineDrag };
}
