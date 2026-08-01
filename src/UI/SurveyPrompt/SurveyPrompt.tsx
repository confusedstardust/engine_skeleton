import { useEffect, useRef, useState } from 'react';
import { NARRATIVEOS_GAME_ENDED_EVENT } from '@/Core/events/gameLifecycle';
import styles from './surveyPrompt.module.scss';

const SURVEY_SHOWN_SESSION_KEY = 'narrativeos:game-survey-shown';
const DEFAULT_SURVEY_URL = 'https://my.feishu.cn/share/base/form/shrcn0hhWX4jndclNCe8nNYCCFf';
const SURVEY_ENABLED = import.meta.env.VITE_GAME_SURVEY_ENABLED?.trim().toLowerCase() !== 'false';
const SURVEY_URL = import.meta.env.VITE_GAME_SURVEY_URL?.trim() || DEFAULT_SURVEY_URL;

export default function SurveyPrompt() {
  const [visible, setVisible] = useState(false);
  const primaryButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!SURVEY_ENABLED) return;

    const showSurvey = () => {
      try {
        if (window.sessionStorage.getItem(SURVEY_SHOWN_SESSION_KEY) === 'true') return;
        window.sessionStorage.setItem(SURVEY_SHOWN_SESSION_KEY, 'true');
      } catch {
        // The prompt still works when session storage is unavailable.
      }
      setVisible(true);
    };

    window.addEventListener(NARRATIVEOS_GAME_ENDED_EVENT, showSurvey);
    return () => window.removeEventListener(NARRATIVEOS_GAME_ENDED_EVENT, showSurvey);
  }, []);

  useEffect(() => {
    if (!visible) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    primaryButtonRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setVisible(false);
    };
    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      previousFocus?.focus();
    };
  }, [visible]);

  if (!SURVEY_ENABLED || !visible) return null;

  const openSurvey = () => {
    window.open(SURVEY_URL, '_blank', 'noopener,noreferrer');
    setVisible(false);
  };

  return (
    <div className={styles.backdrop} role="presentation">
      <section
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="survey-prompt-title"
        aria-describedby="survey-prompt-description"
      >
        <div className={styles.ornament} aria-hidden="true">
          <span />
          <i>终</i>
          <span />
        </div>
        <p className={styles.eyebrow}>THE STORY CONTINUES WITH YOU</p>
        <h2 id="survey-prompt-title">感谢完成本次体验</h2>
        <p id="survey-prompt-description" className={styles.description}>
          欢迎用一分钟告诉我们你的感受。每一条反馈，都会帮助我们把下一场故事做得更好。
        </p>
        <div className={styles.actions}>
          <button type="button" className={styles.skip} onClick={() => setVisible(false)}>
            暂时跳过
          </button>
          <button ref={primaryButtonRef} type="button" className={styles.primary} onClick={openSurvey}>
            填写体验问卷
            <span aria-hidden="true">↗</span>
          </button>
        </div>
      </section>
    </div>
  );
}
