'use client';

import { useEffect, useRef, useState } from 'react';
import type { EChartsCoreOption, EChartsType } from 'echarts/core';

/** Shared chart lifecycle: on-demand library, responsive sizing, canvas and event cleanup. */
export function AnalyticsChart({ option, label, height = 260, onSelect }: { option: EChartsCoreOption; label: string; height?: number; onSelect?: (index: number) => void }) {
  const element = useRef<HTMLDivElement>(null);
  const chart = useRef<EChartsType | null>(null);
  const latestOption = useRef(option);
  const latestSelect = useRef(onSelect);
  const [error, setError] = useState(false);
  latestOption.current = option;
  latestSelect.current = onSelect;
  useEffect(() => {
    let cancelled = false;
    let observer: ResizeObserver | null = null;
    void import('./echarts-runtime').then(runtime => {
      if (cancelled || !element.current) return;
      chart.current = runtime.init(element.current, undefined, { renderer: 'canvas' });
      chart.current.setOption(latestOption.current);
      chart.current.on('click', params => {
        const index = (params as { dataIndex?: number }).dataIndex;
        if (typeof index === 'number') latestSelect.current?.(index);
      });
      observer = new ResizeObserver(() => { if (element.current?.clientWidth) chart.current?.resize(); });
      observer.observe(element.current);
    }).catch(() => { if (!cancelled) setError(true); });
    return () => { cancelled = true; observer?.disconnect(); chart.current?.dispose(); chart.current = null; };
  }, []);
  useEffect(() => { chart.current?.setOption(option, { notMerge: true }); }, [option]);
  return <div className="cq-chart-host" style={{ height }}><div ref={element} role="img" aria-label={label} style={{ width: '100%', height: '100%' }} />{error && <span role="status" className="cq-chart-error">图表暂时不可用，答题明细仍可查看</span>}</div>;
}
