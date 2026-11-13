'use client';



import { Button } from '../../../components/ui/button';
import { ImagePreview } from "../../../components/ui/image-preview";
import { useToast } from '../../../components/ui/toast';
import { forgeApi as api } from '../../../lib/api-client';
import type { QuizResponse } from '../../../domain/quiz';

import { useWorkActions, workTitle, workIsBuilding } from '../../../hooks/use-work-actions';
import type { Job } from '../../../domain/jobs';

import { useConfirmation } from '../../../components/ui/modal';
import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { PublishedFlowModal } from '../../../components/published-flow-modal';

import { withBasePath } from '../../base-path';

export function CompletionPanel(props: { job: Job; playUrl: string; busy: boolean; editDraft: () => void }) {
  const [flowOpen, setFlowOpen] = useState(false);
  const [quiz, setQuiz] = useState<QuizResponse | null>(null);
  const notify = useToast();
  const actions = useWorkActions({ confirm: useConfirmation(), notify });
  const publication = actions.publications[props.job.id];
  const publicationBusy = actions.busy?.action === 'publication';
  const titleBusy = actions.busy?.action === 'title';
  const [gameTitle, setGameTitle] = useState(workTitle(props.job));
  const [titleDraft, setTitleDraft] = useState(gameTitle);
  const [titleEditing, setTitleEditing] = useState(false);
  const titleMessage = actions.errors[`${props.job.id}:title`] || '';
  const currentJobId = useRef(props.job.id);
  currentJobId.current = props.job.id;
  const titleCancelRef = useRef(false);
  const { loadPublication } = actions;
  const { id, status, has_published_build } = props.job;
  useEffect(() => { void loadPublication({ id, status, has_published_build }); }, [loadPublication, id, status, has_published_build]);
  const incomingTitle = workTitle(props.job);
  useEffect(() => {
    setGameTitle(incomingTitle);
    setTitleDraft(incomingTitle);
  }, [id, incomingTitle]);
  useEffect(() => {
    let active = true;
    api<QuizResponse>(`/jobs/${props.job.id}/quiz`)
      .then((value) => {
        if (active) setQuiz(value);
      })
      .catch(() => {
        if (active) setQuiz(null);
      });
    return () => {
      active = false;
    };
  }, [props.job.id]);
  const publishToEcosystem = () => { void actions.changePublication(props.job); };
  const removeFromEcosystem = () => { void actions.changePublication(props.job, true); };
  const saveGameTitle = async () => {
    const updated = await actions.rename(props.job, titleDraft);
    if (updated && updated.id === currentJobId.current) {
      const title = workTitle(updated);
      setGameTitle(title);
      setTitleDraft(title);
      setTitleEditing(false);
    }
  };
  const state = props.job.build_state || 'CURRENT';
  const failed = state === 'FAILED';
  const stale = state === 'STALE' || failed;
  const building = workIsBuilding(props.job);
  return (
    <section className="completion-panel" aria-labelledby="completion-title">
      <div className="completion-game-title">
        {titleEditing ? (
          <div className="completion-title-editor">
            <input
              value={titleDraft}
              maxLength={160}
              autoFocus
              aria-label="游戏名称"
              disabled={building || Boolean(actions.busy)}
              onChange={(event) => setTitleDraft(event.target.value)}
              onBlur={() => {
                if (titleCancelRef.current) {
                  titleCancelRef.current = false;
                  return;
                }
                if (!titleBusy) void saveGameTitle();
              }}
              onKeyDown={(event) => {
                if (event.key === 'Enter') event.currentTarget.blur();
                if (event.key === 'Escape') {
                  titleCancelRef.current = true;
                  setTitleDraft(gameTitle);
                  setTitleEditing(false);
                  actions.clearError(props.job.id, 'title');
                  event.currentTarget.blur();
                }
              }}
            />
          </div>
        ) : (
          <div className="completion-title-display">
            <strong>{gameTitle}</strong>
            <Button variant="unstyled"
              type="button"
              aria-label="修改游戏名称"
              disabled={building || Boolean(actions.busy)}
              title="修改游戏名称"
              onClick={() => {
                setTitleEditing(true);
                actions.clearError(props.job.id, 'title');
              }}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path className="edit-frame" d="M11 4H5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2v-6" />
                <path
                  className="edit-pencil"
                  d="m13.15 5.15 5.7 5.7L9.2 20.5l-5.7 1 1-5.7 9.65-10.65Zm1.42-1.42 2.16-2.16a2 2 0 0 1 2.83 0l2.87 2.87a2 2 0 0 1 0 2.83l-2.16 2.16-5.7-5.7Z"
                />
              </svg>
            </Button>
          </div>
        )}
        {titleMessage ? <small role="status">{titleMessage}</small> : null}
      </div>
      <div className="completion-cover">
        <ImagePreview
          src={withBasePath(`/play/${props.job.id}/cover?revision=${props.job.published_revision ?? 0}&cover=${props.job.cover_revision ?? 0}`)}
          fallback="无封面"
          alt="当前游戏封面"
        />
      </div>
      <div className="completion-copy">
        <h2 id="completion-title">
          {building ? '正在应用修改' : failed ? '修改应用失败' : stale ? '已有草稿修改' : '当前游戏已发布'}
        </h2>
        <dl className="completion-revisions">
          <div>
            <dt>当前发布</dt>
            <dd>R{props.job.published_revision ?? 0}</dd>
          </div>
          <div>
            <dt>编辑草稿</dt>
            <dd>R{props.job.draft_revision ?? 0}</dd>
          </div>
          <div>
            <dt>同步状态</dt>
            <dd>{state}</dd>
          </div>
        </dl>
      </div>
      <div className="completion-actions">
        <a className="btn primary" href={props.playUrl} target="_blank">
          开始游戏
        </a>
        <div className="publication-actions">
          <Button
            variant="outline" className="ecosystem-publish"
            type="button"
            busy={Boolean(publicationBusy)} disabled={building || Boolean(actions.busy) || !publication}
            onClick={publishToEcosystem}
          >
            {publicationBusy ? '正在处理…' : !publication ? '读取发布状态…' : publication.published ? '更新发布' : '发布'}
          </Button>
          {actions.errors[`${props.job.id}:publication`] && <Button variant="outline" disabled={Boolean(actions.busy)} onClick={() => void actions.loadPublication(props.job)}>重试发布状态</Button>}
          {publication?.published ? (
            <Button variant="unstyled"
              className="publication-remove"
              type="button"
              disabled={building || Boolean(actions.busy)}
              onClick={removeFromEcosystem}
            >
              取消生态发布
            </Button>
          ) : null}
        </div>
        <Button variant="outline" type="button" busy={Boolean(props.busy)} disabled={building || props.busy} onClick={props.editDraft}>
          编辑
        </Button>
        <Link className="btn outline" href={`/practice/${props.job.id}`}>
          {quiz?.quiz || quiz?.status === 'READY' ? '打开习题' : '生成习题'}
        </Link>
        <Button variant="outline" type="button" onClick={() => setFlowOpen(true)}>
          流程图
        </Button>
      </div>
      {flowOpen && <PublishedFlowModal job={props.job} onClose={() => setFlowOpen(false)} />}
    </section>
  );
}
