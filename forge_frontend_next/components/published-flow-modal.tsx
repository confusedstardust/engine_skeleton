"use client";
import { useEffect, useRef, useState } from 'react';
import { forgeApi as api } from '../lib/api-client';
import type { Job } from '../domain/jobs';
import { ModalBody, ModalFrame } from './ui/modal';
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
  return (

        <ModalFrame title="最新流程图" onClose={closeFlow}>
          <div className="flow-modal-layer">
            <button className="flow-modal-dismiss" aria-label="关闭流程图" onClick={closeFlow} />
            <ModalBody><section className="flow-modal" ref={flowModalRef}>
              <div className="flow-modal-head">
                <div>
                  <span>已发布版本 · R{graph?.revision ?? props.job.published_revision ?? 0}</span>
                  <h3>最新剧情流程图</h3>
                </div>
                <div className="flow-modal-actions">
                  <button className="btn outline" type="button" autoFocus onClick={closeFlow}>
                    关闭
                  </button>
                </div>
              </div>
              {flowNotice && (
                <p className="flow-fullscreen-notice" role="alert">
                  {flowNotice}
                </p>
              )}
              <div className="flow-modal-body">
                {flowError ? (
                  <p className="error">{flowError}</p>
                ) : graph ? (
                  <StoryFlowView
                    graph={graph}
                    viewportVersion={flowFullscreen ? 1 : 0}
                    fullscreen={flowFullscreen}
                    onToggleFullscreen={toggleFlowFullscreen}
                  />
                ) : (
                  <p>正在加载流程图…</p>
                )}
              </div>
            </section></ModalBody>
          </div>
        </ModalFrame>

  );
}
