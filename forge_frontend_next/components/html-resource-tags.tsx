'use client';
import { useState } from 'react';
import * as ToggleGroup from '@radix-ui/react-toggle-group';
import { Button } from './ui/button';
import styles from './admin-html-resources.module.css';

export type Classification = Record<'curriculum' | 'stage' | 'subject' | 'grade' | 'custom', string[]>;
export type ResourceTaxonomy = Classification;
export const emptyClassification = (): Classification => ({ curriculum: [], stage: [], subject: [], grade: [], custom: [] });
const labels: Record<keyof Classification, string> = { curriculum: '课程体系', stage: '适用学段', subject: '学科领域', grade: '适用年级', custom: '自定义标签' };

export default function HtmlResourceTags({ value, onChange, taxonomy, id }: {
  value: Classification; onChange: (value: Classification) => void; taxonomy: ResourceTaxonomy; id: string;
}) {
  const [drafts, setDrafts] = useState<Partial<Record<keyof Classification, string>>>({});
  function add(key: keyof Classification) {
    const text = (drafts[key] || '').trim();
    if (!text || value[key].length >= 30) return;
    onChange({ ...value, [key]: [...new Set([...value[key], text])] });
    setDrafts(previous => ({ ...previous, [key]: '' }));
  }
  return <div className={styles.classification}>{(Object.keys(labels) as (keyof Classification)[]).map(key => <div className={styles.row} key={key}>
    <span id={`${id}-${key}`}>{labels[key]}{key === 'subject' ? ' *' : ''}</span>
    <div><ToggleGroup.Root type="multiple" value={value[key]} aria-labelledby={`${id}-${key}`} onValueChange={values => onChange({ ...value, [key]: values })} className={styles.choices}>
      {[...new Set([...(taxonomy[key] || []), ...value[key]])].map(text => <ToggleGroup.Item value={text} key={text} asChild><Button variant="unstyled">{text}</Button></ToggleGroup.Item>)}
    </ToggleGroup.Root><div className={styles.addTag}><input aria-label={`添加${labels[key]}`} placeholder={`添加${labels[key]}`} maxLength={40} value={drafts[key] || ''} onChange={event => setDrafts(previous => ({ ...previous, [key]: event.target.value }))} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); add(key); } }} /><Button size="sm" onClick={() => add(key)} disabled={!(drafts[key] || '').trim() || value[key].length >= 30}>添加</Button></div></div>
  </div>)}</div>;
}
