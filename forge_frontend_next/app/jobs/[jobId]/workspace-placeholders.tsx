'use client';
import { Spinner } from '../../../components/ui/state';

import { Button } from '../../../components/ui/button';
export function LoadingPlaceholder({ title, brief }: { title: string; brief: string }) {
  return (
    <div className="node-placeholder loading">
      <Spinner as="div"  aria-hidden="true" />
      <strong>{title}</strong>
      <span>{brief}</span>
    </div>
  );
}

export function FailedPlaceholder(props: {
  title: string;
  brief: string;
  action: () => void;
  actionLabel: string;
  busy: boolean;
}) {
  return (
    <div className="node-placeholder failed-placeholder">
      <span className="failed-mark" aria-hidden="true">
        !
      </span>
      <strong>{props.title}</strong>
      <span>{props.brief}</span>
      <Button variant="primary" className="retry-action" type="button" busy={Boolean(props.busy)} onClick={props.action}>
        <span aria-hidden="true">↻</span>
        {props.busy ? '正在重试...' : props.actionLabel}
      </Button>
    </div>
  );
}
