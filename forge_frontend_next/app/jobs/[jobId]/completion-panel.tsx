'use client';

import { useToast } from '../../../components/ui/toast';
import { forgeApi as api } from '../../../lib/api-client';
import type { QuizResponse } from '../../../domain/quiz';

import type { Job } from '../../../domain/jobs';

import { useConfirmation } from '../../../components/ui/modal';
import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { PublishedFlowModal } from '../../../components/published-flow-modal';

import { withBasePath } from '../../base-path';

type PublicationResponse = {
  published: boolean;
  work?: {
    title: string;
    playUrl: string;
  };
};

export function CompletionPanel(props: { job: Job; playUrl: string; busy: boolean; editDraft: () => void }) {
  const [flowOpen, setFlowOpen] = useState(false);
  const [publication, setPublication] = useState<PublicationResponse | null>(null);
  const [quiz, setQuiz] = useState<QuizResponse | null>(null);
  const [publicationBusy, setPublicationBusy] = useState(false);
  const notify = useToast();
  const [gameTitle, setGameTitle] = useState(
    props.job.title?.trim() ||
      String(props.job.options?.classroom_topic || '').trim() ||
      props.job.source_material?.split(/\r?\n/)[0]?.trim() ||
      '未命名游戏',
  );
  const [titleDraft, setTitleDraft] = useState(gameTitle);
  const [titleEditing, setTitleEditing] = useState(false);
  const confirm = useConfirmation();
  const [titleBusy, setTitleBusy] = useState(false);
  const [titleMessage, setTitleMessage] = useState('');
  const titleCancelRef = useRef(false);
  useEffect(() => {
    let active = true;
    api<PublicationResponse>(`/jobs/${props.job.id}/ecosystem-publication`)
      .then((value) => {
        if (active) setPublication(value);
      })
      .catch(() => {
        if (active) setPublication(null);
      });
    return () => {
      active = false;
    };
  }, [props.job.id]);
  useEffect(() => {
    const nextTitle =
      props.job.title?.trim() ||
      String(props.job.options?.classroom_topic || '').trim() ||
      props.job.source_material?.split(/\r?\n/)[0]?.trim() ||
      '未命名游戏';
    setGameTitle(nextTitle);
    setTitleDraft(nextTitle);
  }, [props.job.id, props.job.options?.classroom_topic, props.job.source_material, props.job.title]);
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
  const publishToEcosystem = async () => {
    setPublicationBusy(true);
    try {
      const value = await api<PublicationResponse>(`/jobs/${props.job.id}/ecosystem-publication`, {
        method: 'POST',
        body: JSON.stringify({}),
      });
      setPublication(value);
      notify('发布成功，作品已经出现在教师资源广场中。', 'success');
    } catch (error) {
      notify(error instanceof Error ? error.message : '发布失败，请稍后重试。', 'error');
    } finally {
      setPublicationBusy(false);
    }
  };
  const removeFromEcosystem = async () => {
    if (!(await confirm('确定从教师资源广场中取消发布吗？游戏本身不会被删除。'))) return;
    setPublicationBusy(true);
    try {
      const value = await api<PublicationResponse>(`/jobs/${props.job.id}/ecosystem-publication`, { method: 'DELETE' });
      setPublication(value);
      notify('已从教师资源广场中取消发布。', 'success');
    } catch (error) {
      notify(error instanceof Error ? error.message : '取消发布失败，请稍后重试。', 'error');
    } finally {
      setPublicationBusy(false);
    }
  };
  const saveGameTitle = async () => {
    const title = titleDraft.trim();
    if (!title) {
      setTitleDraft(gameTitle);
      setTitleEditing(false);
      setTitleMessage('');
      return;
    }
    setTitleBusy(true);
    setTitleMessage('');
    try {
      const value = await api<{ job: Job }>(`/jobs/${props.job.id}/title`, {
        method: 'PUT',
        body: JSON.stringify({ title }),
      });
      const savedTitle = value.job.title?.trim() || title;
      setGameTitle(savedTitle);
      setTitleDraft(savedTitle);
      setTitleEditing(false);
      setTitleMessage('');
    } catch (error) {
      setTitleMessage(error instanceof Error ? error.message : '游戏名称保存失败');
    } finally {
      setTitleBusy(false);
    }
  };
  const state = props.job.build_state || 'CURRENT';
  const failed = state === 'FAILED';
  const stale = state === 'STALE' || failed;
  const building = state === 'BUILDING' || props.job.status === 'RUNNING' || props.job.status === 'QUEUED';
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
                  setTitleMessage('');
                  event.currentTarget.blur();
                }
              }}
            />
          </div>
        ) : (
          <div className="completion-title-display">
            <strong>{gameTitle}</strong>
            <button
              type="button"
              aria-label="修改游戏名称"
              title="修改游戏名称"
              onClick={() => {
                setTitleEditing(true);
                setTitleMessage('');
              }}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path className="edit-frame" d="M11 4H5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2v-6" />
                <path
                  className="edit-pencil"
                  d="m13.15 5.15 5.7 5.7L9.2 20.5l-5.7 1 1-5.7 9.65-10.65Zm1.42-1.42 2.16-2.16a2 2 0 0 1 2.83 0l2.87 2.87a2 2 0 0 1 0 2.83l-2.16 2.16-5.7-5.7Z"
                />
              </svg>
            </button>
          </div>
        )}
        {titleMessage ? <small role="status">{titleMessage}</small> : null}
      </div>
      <div className="completion-cover">
        <img
          src={withBasePath(`/play/${props.job.id}/cover?revision=${props.job.published_revision ?? 0}`)}
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
          <button
            className="btn ecosystem-publish"
            type="button"
            disabled={building || publicationBusy}
            onClick={publishToEcosystem}
          >
            {publicationBusy ? '正在处理…' : publication?.published ? '更新发布' : '发布'}
          </button>
          {publication?.published ? (
            <button
              className="publication-remove"
              type="button"
              disabled={publicationBusy}
              onClick={removeFromEcosystem}
            >
              取消生态发布
            </button>
          ) : null}
        </div>
        <button className="btn outline" type="button" disabled={building || props.busy} onClick={props.editDraft}>
          编辑
        </button>
        <Link className="btn outline" href={`/practice/${props.job.id}`}>
          {quiz?.quiz || quiz?.status === 'READY' ? '打开习题' : '生成习题'}
        </Link>
        <button className="btn outline" type="button" onClick={() => setFlowOpen(true)}>
          流程图
        </button>
      </div>
      {flowOpen && <PublishedFlowModal job={props.job} onClose={() => setFlowOpen(false)} />}
    </section>
  );
}
