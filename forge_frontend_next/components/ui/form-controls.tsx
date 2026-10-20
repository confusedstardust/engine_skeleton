'use client';

import * as Select from '@radix-ui/react-select';
import * as Slider from '@radix-ui/react-slider';
import type { ReactNode } from 'react';

export type SelectOption = { value: string; label: string; disabled?: boolean };

export function FormSelect(props: {
  value: string;
  options: SelectOption[];
  onValueChange: (value: string) => void;
  disabled?: boolean;
  ariaLabel: string;
  id?: string;
  renderValue?: ReactNode;
  renderOption?: (option: SelectOption) => ReactNode;
  renderOptionSuffix?: (option: SelectOption) => ReactNode;
  leading?: ReactNode;
  menuHeader?: ReactNode;
  side?: 'top' | 'bottom';
  sideOffset?: number;
  collisionPadding?: number;
  classes?: {
    trigger?: string;
    content?: string;
    viewport?: string;
    option?: string;
    chevron?: string;
    check?: string;
  };
}) {
  const emptyValue = '__form_select_empty__';
  return (
    <Select.Root
      value={props.value || emptyValue}
      onValueChange={(value) => props.onValueChange(value === emptyValue ? '' : value)}
      disabled={props.disabled}
    >
      <Select.Trigger
        id={props.id}
        type="button"
        className={props.classes?.trigger || 'ui-select-trigger'}
        aria-label={props.ariaLabel}
      >
        {props.leading}
        <Select.Value>{props.renderValue}</Select.Value>
        <Select.Icon className={props.classes?.chevron || 'ui-select-chevron'} aria-hidden="true">
          ⌄
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Content
          className={props.classes?.content || 'ui-select-content'}
          position="popper"
          side={props.side || 'bottom'}
          align="start"
          sideOffset={props.sideOffset ?? 5}
          collisionPadding={props.collisionPadding ?? 12}
        >
          <Select.Viewport className={props.classes?.viewport ?? 'ui-select-viewport'}>
            {props.menuHeader}
            {props.options.map((option) => (
              <Select.Item
                className={props.classes?.option || 'ui-select-item'}
                key={option.value || emptyValue}
                value={option.value || emptyValue}
                disabled={option.disabled}
                textValue={option.label}
              >
                <Select.ItemText>{props.renderOption?.(option) ?? option.label}</Select.ItemText>
                {props.renderOptionSuffix?.(option)}
                <Select.ItemIndicator className={props.classes?.check || 'ui-select-check'}>✓</Select.ItemIndicator>
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
      <span>
        {props.label}
        <output>{props.value}</output>
      </span>
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
        <Slider.Track className="ui-slider-track">
          <Slider.Range className="ui-slider-range" />
        </Slider.Track>
        <Slider.Thumb className="ui-slider-thumb" />
      </Slider.Root>
    </label>
  );
}
