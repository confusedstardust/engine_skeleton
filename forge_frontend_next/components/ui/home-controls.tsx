"use client";
import * as Select from "@radix-ui/react-select";
import * as Tooltip from "@radix-ui/react-tooltip";
import type { ReactNode } from "react";

export function ModelSelect<T extends string>({ value, onChange, items, disabled, label, image = false }: { value: T; onChange: (value: T) => void; items: { id: T; name: string; model: string; note: string; disabled?: boolean }[]; disabled?: boolean; label: string; image?: boolean }) {
  const current = items.find(item => item.id === value);
  return <Select.Root value={value} onValueChange={(next) => onChange(next as T)} disabled={disabled}>
    <Select.Trigger className="home-model-trigger" aria-label={label}><span className={image ? "image-model-dot" : "model-spark"} aria-hidden="true">{image ? "" : "✦"}</span><Select.Value>{current?.name}</Select.Value><Select.Icon className="model-chevron">⌄</Select.Icon></Select.Trigger>
    <Select.Portal><Select.Content className="model-menu home-model-menu" position="popper" side="top" sideOffset={9} collisionPadding={16}><Select.Viewport><div className="model-menu-label">{label}</div>{items.map(item => <Select.Item key={item.id} value={item.id} disabled={item.disabled} className="home-model-option"><Select.ItemText><span className="model-option-copy"><strong>{item.name}</strong><small>{item.note}</small></span></Select.ItemText><span className="model-option-id">{item.disabled ? "暂不可用" : item.model}</span><Select.ItemIndicator className="model-check">✓</Select.ItemIndicator></Select.Item>)}</Select.Viewport></Select.Content></Select.Portal>
  </Select.Root>;
}
export function ActionHint({ text, children }: { text?: string; children: ReactNode }) {
  if (!text) return <>{children}</>;
  return <Tooltip.Provider delayDuration={250}><Tooltip.Root><Tooltip.Trigger asChild><span className="action-hint-trigger" tabIndex={0}>{children}</span></Tooltip.Trigger><Tooltip.Portal><Tooltip.Content className="action-hint-content" sideOffset={6}>{text}<Tooltip.Arrow /></Tooltip.Content></Tooltip.Portal></Tooltip.Root></Tooltip.Provider>;
}
