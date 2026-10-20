'use client';

import * as Tooltip from '@radix-ui/react-tooltip';
import { isValidElement, type ReactNode } from 'react';

export function ActionHint({ text, children }: { text?: string; children: ReactNode }) {
  if (!text) return <>{children}</>;
  // Enabled controls are already focusable. Disabled controls need a focusable
  // wrapper so keyboard users can still discover why an action is unavailable.
  const direct =
    isValidElement<{ disabled?: boolean }>(children) &&
    typeof children.type === 'string' &&
    ['button', 'a', 'input'].includes(children.type) &&
    !children.props.disabled;
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
