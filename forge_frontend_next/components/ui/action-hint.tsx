'use client';

import * as Tooltip from '@radix-ui/react-tooltip';
import { isValidElement, type ReactNode } from 'react';
import { Button, type ButtonProps } from './button';

export function ActionHint({ text, children }: { text?: string; children: ReactNode }) {
  if (!text) return <>{children}</>;
  // Enabled controls are already focusable. Disabled controls need a focusable
  // wrapper so keyboard users can still discover why an action is unavailable.
  const direct =
    isValidElement<ButtonProps>(children) &&
    ((typeof children.type === 'string' && ['button', 'a', 'input'].includes(children.type)) || children.type === Button) &&
    !children.props.disabled && !children.props.busy && children.props['aria-busy'] !== true && children.props['aria-busy'] !== 'true';
  return (
    <Tooltip.Provider delayDuration={250}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          {direct ? (
            children
          ) : (
            <span className="action-hint-trigger" tabIndex={0}>
              {children}
            </span>
          )}
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content className="action-hint-content" sideOffset={6}>
            {text}
            <Tooltip.Arrow />
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  );
}
