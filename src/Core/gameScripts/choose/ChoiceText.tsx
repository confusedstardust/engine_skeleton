import React from 'react';
import { css } from '@emotion/css';
import { compileSentence } from '@/Core/parser/compileSentence';

export function hasChoiceMarkup(text: string) {
  return /\[[^\[\]]*\]\([^()]*\)/.test(text);
}

export function ChoiceText({ text }: { text: string }) {
  if (!hasChoiceMarkup(text)) return <>{text}</>;
  // ChooseOption has already unescaped literal pipes; they are not line separators here.
  const lines = compileSentence(text.replace(/\|/g, '\\|'), 0, true, false);
  return <>{lines.flat().map((node, index) => {
    const values = node.enhancedValue ?? [];
    const inlineStyle = values.filter(value => value.key === 'style' || value.key === 'style-alltext').map(value => value.value).join(';');
    return <span key={index} className={inlineStyle ? css(inlineStyle) : undefined} title={values.find(value => value.key === 'tips')?.value}>{node.reactNode}</span>;
  })}</>;
}
