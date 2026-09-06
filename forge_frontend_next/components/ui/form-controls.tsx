"use client";

import * as Select from "@radix-ui/react-select";
import * as Slider from "@radix-ui/react-slider";

export type SelectOption = { value: string; label: string };

export function FormSelect(props: {
  value: string;
  options: SelectOption[];
  onValueChange: (value: string) => void;
  disabled?: boolean;
  ariaLabel: string;
}) {
  const emptyValue = "__form_select_empty__";
  return (
    <Select.Root value={props.value || emptyValue} onValueChange={(value) => props.onValueChange(value === emptyValue ? "" : value)} disabled={props.disabled}>
      <Select.Trigger className="ui-select-trigger" aria-label={props.ariaLabel}>
        <Select.Value />
        <Select.Icon className="ui-select-chevron" aria-hidden="true">⌄</Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Content className="ui-select-content" position="popper" sideOffset={5}>
          <Select.Viewport>
            {props.options.map((option) => (
              <Select.Item className="ui-select-item" key={option.value || emptyValue} value={option.value || emptyValue}>
                <Select.ItemText>{option.label}</Select.ItemText>
                <Select.ItemIndicator className="ui-select-check">✓</Select.ItemIndicator>
              </Select.Item>
            ))}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  );
}

export function FormSlider(props: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onValueChange: (value: number) => void;
  disabled?: boolean;
}) {
  return (
    <label className="ui-slider-field">
      <span>{props.label}<output>{props.value}</output></span>
      <Slider.Root
        className="ui-slider-root"
        value={[props.value]}
        min={props.min}
        max={props.max}
        step={props.step}
        disabled={props.disabled}
        onValueChange={([value]) => props.onValueChange(value)}
        aria-label={props.label}
      >
        <Slider.Track className="ui-slider-track"><Slider.Range className="ui-slider-range" /></Slider.Track>
        <Slider.Thumb className="ui-slider-thumb" />
      </Slider.Root>
    </label>
  );
}
