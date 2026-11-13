'use client';

import { FormSelect } from './ui/form-controls';
import type { Assignment } from '../domain/classroom-quiz';

export function assignmentRound(assignments: Assignment[], assignment: Assignment) {
  const siblings = assignments.filter(a => (a.class_id || a.class_name) === (assignment.class_id || assignment.class_name))
    .sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id));
  return siblings.findIndex(a => a.id === assignment.id) + 1;
}

export function assignmentTime(value: string) {
  return new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
}

export function AssignmentPicker({ assignments, selected, onChange, disabled }: { assignments: Assignment[]; selected: string; onChange: (id: string) => void; disabled: boolean }) {
  const current = assignments.find(a => a.id === selected);
  return <FormSelect ariaLabel="班级练习" value={selected} onValueChange={onChange} disabled={disabled}
    options={assignments.map(a => ({ value: a.id, label: `${a.class_name} · 第 ${assignmentRound(assignments, a)} 次练习 · ${assignmentTime(a.created_at)}` }))}
    leading={<span className="cq-class-icon" aria-hidden="true">▦</span>}
    renderValue={<span className="cq-assignment-value"><strong>{current?.class_name || '选择班级练习'}</strong><span>{current ? `第 ${assignmentRound(assignments, current)} 次练习 · ${assignmentTime(current.created_at)}` : '请选择'}</span></span>}
    renderOption={option => {
      const a = assignments.find(a => a.id === option.value)!;
      return <><span className="cq-assignment-item-top"><strong>{a.class_name}</strong><span>第 {assignmentRound(assignments, a)} 次</span><small>{a.submitted_count} 份答卷</small></span><span className="cq-assignment-item-title">{a.name}</span><span className="cq-assignment-item-time">{assignmentTime(a.created_at)} · {a.status === 'OPEN' ? '开放中' : '已关闭'}</span></>;
    }}
    sideOffset={8} collisionPadding={16}
    classes={{ trigger: 'cq-assignment-trigger', content: 'cq-assignment-menu', option: 'cq-assignment-item', chevron: 'cq-chevron', check: 'cq-assignment-check' }} />;
}
