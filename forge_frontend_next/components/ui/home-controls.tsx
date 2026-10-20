'use client';
import { FormSelect } from './form-controls';
export { ActionHint } from './action-hint';

type ModelOption<T> = { id: T; name: string; model: string; note: string; disabled?: boolean };
export function ModelSelect<T extends string>({
  value,
  onChange,
  items,
  disabled,
  label,
  image = false,
}: {
  value: T;
  onChange: (value: T) => void;
  items: ModelOption<T>[];
  disabled?: boolean;
  label: string;
  image?: boolean;
}) {
  return (
    <FormSelect
      value={value}
      onValueChange={(next) => onChange(next as T)}
      disabled={disabled}
      ariaLabel={label}
      options={items.map((item) => ({ value: item.id, label: item.name, disabled: item.disabled }))}
      renderValue={items.find((item) => item.id === value)?.name}
      leading={
        <span className={image ? 'image-model-dot' : 'model-spark'} aria-hidden="true">
          {image ? '' : '✦'}
        </span>
      }
      menuHeader={<div className="model-menu-label">{label}</div>}
      side="top"
      sideOffset={9}
      collisionPadding={16}
      classes={{
        trigger: 'home-model-trigger',
        content: 'model-menu home-model-menu',
        option: 'home-model-option',
        chevron: 'model-chevron',
        check: 'model-check',
        viewport: '',
      }}
      renderOption={(option) => {
        const item = items.find((item) => item.id === option.value)!;
        return (
          <span className="model-option-copy">
            <strong>{item.name}</strong>
            <small>{item.note}</small>
          </span>
        );
      }}
      renderOptionSuffix={(option) => {
        const item = items.find((item) => item.id === option.value)!;
        return <span className="model-option-id">{item.disabled ? '暂不可用' : item.model}</span>;
      }}
    />
  );
}
