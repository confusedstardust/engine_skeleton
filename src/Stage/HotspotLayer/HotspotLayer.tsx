import React, { FC, MouseEvent, useEffect, useMemo, useState } from 'react';
import { useStageState } from '@/hooks/useStageState';
import styles from './hotspotLayer.module.scss';

interface IHotspot {
  bg: string;
  location: string;
  obj: string;
  knowledge: string;
  title?: string;
  w?: number | string;
  h?: number | string;
}

interface IPosition {
  x: number;
  y: number;
  w: number;
  h: number;
}

const HOTSPOT_URL = './game/hotspots.json';
const DEFAULT_SIZE = 6;

function fileNameOf(value: string): string {
  return value.replace(/\\/g, '/').split('/').pop() || value;
}

function toPercent(value: string | number | undefined, fallback: number): number {
  if (value === undefined || value === null || value === '') return fallback;
  const parsed = typeof value === 'number' ? value : Number.parseFloat(String(value));
  if (!Number.isFinite(parsed)) return fallback;
  return parsed <= 1 ? parsed * 100 : parsed;
}

function parsePosition(hotspot: IHotspot): IPosition {
  const [rawX, rawY] = hotspot.location.split(',').map((item) => item.trim());
  return {
    x: toPercent(rawX, 50),
    y: toPercent(rawY, 50),
    w: toPercent(hotspot.w, DEFAULT_SIZE),
    h: toPercent(hotspot.h, DEFAULT_SIZE),
  };
}

function hotspotKey(hotspot: IHotspot, index: number): string {
  return `${hotspot.bg}:${hotspot.obj}:${hotspot.location}:${index}`;
}

export const HotspotLayer: FC = () => {
  const stageState = useStageState();
  const [hotspots, setHotspots] = useState<IHotspot[]>([]);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [burstKey, setBurstKey] = useState<string | null>(null);
  const [visited, setVisited] = useState<Record<string, boolean>>({});

  useEffect(() => {
    let cancelled = false;
    fetch(HOTSPOT_URL)
      .then((response) => {
        if (!response.ok) return [];
        return response.json();
      })
      .then((data) => {
        if (!cancelled && Array.isArray(data)) {
          setHotspots(data);
        }
      })
      .catch(() => {
        if (!cancelled) setHotspots([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const currentBg = fileNameOf(stageState.bgName);
  const visibleHotspots = useMemo(
    () => hotspots.filter((hotspot) => fileNameOf(hotspot.bg) === currentBg),
    [currentBg, hotspots],
  );
  const activeHotspot = visibleHotspots.find((hotspot, index) => hotspotKey(hotspot, index) === activeKey);

  useEffect(() => {
    setActiveKey(null);
  }, [currentBg]);

  if (!visibleHotspots.length) return null;

  const close = (event: MouseEvent<HTMLDivElement>) => {
    event.stopPropagation();
    setActiveKey(null);
  };

  return (
    <div className={`${styles.layer} ${activeKey ? styles.layerActive : ''}`} onClick={close}>
      {visibleHotspots.map((hotspot, index) => {
        const key = hotspotKey(hotspot, index);
        const position = parsePosition(hotspot);
        const isVisited = Boolean(visited[key]);
        return (
          <button
            key={key}
            type="button"
            className={`${styles.hotspot} ${isVisited ? styles.hotspotVisited : ''} ${
              burstKey === key ? styles.hotspotBurst : ''
            }`}
            title={hotspot.obj}
            aria-label={hotspot.obj}
            style={{
              left: `${position.x}%`,
              top: `${position.y}%`,
              width: `${position.w}%`,
              height: `${position.h}%`,
            }}
            onClick={(event) => {
              event.stopPropagation();
              setVisited((prev) => ({ ...prev, [key]: true }));
              setActiveKey(key);
              setBurstKey(key);
              window.setTimeout(() => setBurstKey((current) => (current === key ? null : current)), 620);
            }}
          >
            <span className={styles.hotspotPulse} />
          </button>
        );
      })}
      {activeHotspot && (
        <div className={styles.card} role="dialog" aria-modal="false" onClick={(event) => event.stopPropagation()}>
          <div className={styles.cardTitle}>{activeHotspot.title || activeHotspot.obj}</div>
          <div className={styles.cardText}>
            {activeHotspot.knowledge.split(/\r?\n/).map((line, index) => (
              <p key={`${activeKey}-line-${index}`}>{line}</p>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
