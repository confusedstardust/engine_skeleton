"use client";
import { LoadingState } from './ui/state';
import { InlineFeedback } from './ui/feedback';

import { useEffect, useRef, useState } from 'react';
import { forgeApi as api } from '../lib/api-client';
import type { Job } from '../domain/jobs';
import { ContentDialog } from './ui/content-dialog';
import { StoryFlowView } from './story-flow-view';
import type { StoryGraph } from './story-graph-data';
export function PublishedFlowModal(props: { job: Job; onClose: () => void }) {
  const [graph, setGraph] = useState<StoryGraph | null>(null);
  const [flowError, setFlowError] = useState('');
  const [flowNotice, setFlowNotice] = useState('');
  const [flowFullscreen, setFlowFullscreen] = useState(false);
  const flowModalRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    let active = true;
    setGraph(null);
    setFlowError('');
    setFlowNotice('');
    api<StoryGraph>(`/jobs/${props.job.id}/published-flow`)
      .then((value) => {
        if (active) setGraph(value);
      })
      .catch((error) => {
        if (active) setFlowError(error instanceof Error ? error.message : '流程图加载失败');
      });
    const fullscreenChange = () => setFlowFullscreen(document.fullscreenElement === flowModalRef.current);
    document.addEventListener('fullscreenchange', fullscreenChange);
    return () => {
      active = false;
      document.removeEventListener('fullscreenchange', fullscreenChange);
    };
  }, [props.job.id, props.job.published_revision]);
  const closeFlow = () => {
    if (document.fullscreenElement === flowModalRef.current) {
      void document
        .exitFullscreen()
        .catch(() => undefined)
        .finally(() => props.onClose());
      return;
    }
    props.onClose();
  };
  const toggleFlowFullscreen = () => {
    const modal = flowModalRef.current;
    if (!modal) return;
    setFlowNotice('');
    if (document.fullscreenElement === modal) {
      void document.exitFullscreen().catch(() => setFlowNotice('退出全屏失败，请按 Esc 重试。'));
      return;
    }
    if (!modal.requestFullscreen) {
      setFlowNotice('当前浏览器不支持全屏查看。可以使用浏览器自身的全屏功能。');
      return;
    }
    void modal.requestFullscreen().catch(() => setFlowNotice('浏览器未允许进入全屏，请检查权限后重试。'));
  };
  return <ContentDialog title="最新剧情流程图" subtitle={`已发布版本 · R${graph?.revision ?? props.job.published_revision ?? 0}`} onClose={closeFlow}
    layerClassName="flow-modal-layer" className="flow-modal" headerClassName="flow-modal-head" bodyClassName="flow-modal-body" panelRef={flowModalRef}
    notice={flowNotice && <InlineFeedback className="flow-feedback-layout" >{flowNotice}</InlineFeedback>}>
                {flowError ? (
                  <InlineFeedback>{flowError}</InlineFeedback>
                ) : graph ? (
                  <StoryFlowView
                    graph={graph}
                    viewportVersion={flowFullscreen ? 1 : 0}
                    fullscreen={flowFullscreen}
                    onToggleFullscreen={toggleFlowFullscreen}
                  />
                ) : (
                  <LoadingState>正在加载流程图…</LoadingState>
                )}
  </ContentDialog>;
}
