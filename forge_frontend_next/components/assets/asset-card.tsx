'use client';

import type { ReactNode } from 'react';
import { CollectionCard, type CardAction } from '@narrativeos/ui/collection-card';
import { Button } from '../ui/button';

type Content = { name: string; preview: ReactNode };
type AssetCardProps = Content & (
  | { variant: 'library'; kind: string; category: string; actions: CardAction[]; controls: ReactNode }
  | { variant: 'picker'; selected: boolean; disabled?: boolean; onSelect: () => void }
  | { variant: 'workbench'; description?: string; ready: boolean; onOpen: () => void; footer?: ReactNode }
);

type CardContentProps = Content & {
  previewClass: string;
  bodyClass: string;
  copyClass?: string;
  nameClass?: string;
  heading?: boolean;
  kind?: string;
  description?: string;
  leading?: ReactNode;
  trailing?: ReactNode;
};

// All card modes share preview, name and metadata rendering; only their outer
// interaction differs (collection menu, selection button or editor button).
function AssetCardContent({ name, preview, previewClass, bodyClass, copyClass, nameClass,
  heading, kind, description, leading, trailing }: CardContentProps) {
  const Name = heading ? 'h2' : 'strong';
  const nameNode = <Name>{name}</Name>;
  const copy = <>{nameClass ? <div className={nameClass}>{nameNode}</div> : nameNode}{description && <small>{description}</small>}</>;
  return <>
    <div className={previewClass} data-asset-kind={kind}>{preview}</div>
    <div className={bodyClass}>{leading}{copyClass ? <div className={copyClass}>{copy}</div> : copy}{trailing}</div>
  </>;
}

export function AssetCard(props: AssetCardProps) {
  if (props.variant === 'picker') return <Button variant="unstyled" className={`asset-library-picker-card ${props.selected ? 'selected' : ''}`}
    role="option" aria-selected={props.selected} disabled={props.disabled} onClick={props.onSelect}>
    <AssetCardContent name={props.name} preview={props.preview} previewClass="asset-library-picker-preview" bodyClass="asset-library-picker-copy" />
    <i aria-hidden="true">✓</i>
  </Button>;

  if (props.variant === 'workbench') return <article className={`asset-card ${props.footer ? 'has-voice' : ''}`}>
    <Button variant="unstyled" className="asset-card-open" onClick={props.onOpen}>
      <AssetCardContent name={props.name} preview={props.preview} previewClass="asset-thumb"
        bodyClass="asset-card-body" copyClass="asset-card-text" description={props.description}
        trailing={<em className={props.ready ? 'ready' : ''}>{props.ready ? '已生成' : '待生成'}</em>} />
    </Button>{props.footer}
  </article>;

  return <CollectionCard className="asset-library-card" menuLabel={`素材操作：${props.name}`} actions={props.actions}>
    <AssetCardContent name={props.name} preview={props.preview} previewClass="asset-library-preview" kind={props.kind}
      bodyClass="asset-library-card-body" copyClass="asset-library-card-copy" nameClass="asset-name-display" heading
      leading={<div className="asset-library-card-top"><span className="asset-kind">{props.category}</span>
        <div className="asset-library-card-actions">{props.controls}</div></div>} />
  </CollectionCard>;
}
