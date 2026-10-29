'use client';

import { FormSelect } from './ui/form-controls';

export function QuizCountRange({ min, max, disabled, onChange }: { min: number; max: number; disabled?: boolean; onChange: (min: number, max: number) => void }) {
  const options = [[4, 6], [6, 10], [10, 15], [15, 20]].map(([low, high]) => ({ value: `${low}-${high}`, label: `${low}–${high} 题` }));
  return <div className="quiz-count-range" role="group" aria-label="生成题目数量范围">
    <span>题目数</span>
    <FormSelect ariaLabel="题目数" value={`${min}-${max}`} options={options} disabled={disabled} onValueChange={value => { const [low, high] = value.split('-').map(Number); onChange(low, high); }} />
  </div>;
}
