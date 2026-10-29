'use client';

import { useMemo } from 'react';
import type { EChartsCoreOption } from 'echarts/core';
import type { QuizStatistics } from '../../domain/classroom-quiz';
import { AnalyticsChart } from './chart';
import { analyticsTheme as theme } from './theme';

type Question = QuizStatistics['questions'][number];
export const optionColors = theme.options;
const chartText = { fontFamily: theme.bodyFont, color: theme.muted };

/** Closed-answer templates share the same data contract and drill-down behavior. */
export function QuestionDistributionChart({ question, onOption }: { question: Question; onOption: (id: string) => void }) {
  const option = useMemo<EChartsCoreOption>(() => {
    const common = { textStyle: chartText, animationDuration: 300, tooltip: { trigger: 'item', renderMode: 'richText' as const } };
    if (question.type === 'judgement') return {
      ...common,
      color: optionColors,
      legend: { bottom: 0, itemWidth: 9, itemHeight: 9, icon: 'circle', textStyle: chartText },
      series: [{ type: 'pie', radius: ['48%', '73%'], center: ['50%', '44%'], stillShowZeroSum: false,
        itemStyle: { borderColor: theme.paper, borderWidth: 3, borderRadius: 4 },
        label: { show: Boolean(question.total), formatter: '{b}\n{d}%', color: theme.muted, fontSize: 11, lineHeight: 18 },
        data: question.options.map(o => ({ value: o.count, name: o.text })), emphasis: { scaleSize: 5 } }],
    };
    return {
      ...common,
      grid: { left: 30, right: 52, top: 14, bottom: 16 },
      xAxis: { type: 'value', min: 0, max: Math.max(1, question.total), minInterval: 1, show: false },
      yAxis: { type: 'category', inverse: true, data: question.options.map(o => o.id), axisTick: { show: false }, axisLine: { show: false }, axisLabel: { color: theme.muted, fontWeight: 600 } },
      series: [{ type: 'bar', barWidth: 20, showBackground: true, backgroundStyle: { color: theme.track, borderRadius: 5 },
        itemStyle: { borderRadius: 5 }, label: { show: true, position: 'right', formatter: '{c} 人', color: theme.muted, fontSize: 11 },
        data: question.options.map((o, i) => ({ value: o.count, name: o.text, itemStyle: { color: optionColors[i] } })) }],
    };
  }, [question]);
  return <AnalyticsChart option={option} height={230} label={question.type === 'judgement' ? '判断题选项环形图' : '单选题选项条形图'} onSelect={i => { const id = question.options[i]?.id; if (id) onOption(id); }} />;
}

export function CorrectnessChart({ questions, selected, onQuestion }: { questions: Question[]; selected?: string; onQuestion: (id: string) => void }) {
  const option = useMemo<EChartsCoreOption>(() => ({
    textStyle: chartText, animationDuration: 300,
    grid: { left: 40, right: 18, top: 30, bottom: 34 },
    tooltip: { trigger: 'axis', renderMode: 'richText', axisPointer: { type: 'shadow' }, valueFormatter: (value: unknown) => `${value}%` },
    xAxis: { type: 'category', data: questions.map((_, i) => `第${i + 1}题`), axisTick: { show: false }, axisLine: { lineStyle: { color: theme.border } }, axisLabel: { fontSize: 11, color: theme.subtle } },
    yAxis: { type: 'value', min: 0, max: 100, interval: 25, axisLabel: { formatter: '{value}%', color: theme.subtle, fontSize: 10 }, splitLine: { lineStyle: { color: theme.grid, type: 'dashed' } } },
    series: [{ name: '正确率', type: 'bar', barMaxWidth: 32, itemStyle: { borderRadius: [5, 5, 0, 0] }, label: { show: true, position: 'top', formatter: '{c}%', fontSize: 10, color: theme.muted },
      data: questions.map(q => ({ value: q.correct_rate === null ? null : Math.round(q.correct_rate * 100), itemStyle: { color: q.id === selected ? theme.accent : theme.accentSoft } })) }],
  }), [questions, selected]);
  return <AnalyticsChart option={option} label="逐题正确率图表" onSelect={i => { const id = questions[i]?.id; if (id) onQuestion(id); }} />;
}

export function AnswerOverviewChart({ correct, incorrect }: { correct: number; incorrect: number }) {
  const total = correct + incorrect;
  const option = useMemo<EChartsCoreOption>(() => ({
    textStyle: chartText, color: [theme.correct, theme.incorrect], animationDuration: 300,
    tooltip: { trigger: 'item', renderMode: 'richText' },
    graphic: [{ type: 'text', left: 'center', top: '35%', style: { text: total ? String(total) : '—', fontSize: 30, fontWeight: 650, fill: theme.ink, fontFamily: theme.numberFont } }, { type: 'text', left: 'center', top: '51%', style: { text: '有效回答', fontSize: 11, fill: theme.subtle } }],
    legend: { bottom: 4, itemWidth: 9, itemHeight: 9, icon: 'circle', textStyle: chartText },
    series: [{ type: 'pie', radius: ['57%', '76%'], center: ['50%', '43%'], stillShowZeroSum: false, label: { show: false }, itemStyle: { borderColor: theme.paper, borderWidth: 3, borderRadius: 4 }, data: [{ name: '正确', value: correct }, { name: '错误', value: incorrect }] }],
  }), [correct, incorrect, total]);
  return <AnalyticsChart option={option} label={total ? `作答分布：正确${correct}次，错误${incorrect}次` : '暂无作答数据'} />;
}
