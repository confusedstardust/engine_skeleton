
import { DataTable } from './ui/table';
import { Button } from './ui/button';
import { EmptyState } from './ui/state';
import type { Submission } from '../domain/classroom-quiz';

export function SubmissionTable({ rows, busy, onView, filtered }: { rows: Submission[]; busy: boolean; onView: (id: string) => void; filtered: boolean }) {
  return <div className="cq-table-wrap"><DataTable density="compact" stickyHeader className="cq-data-table"><thead><tr><th className="cq-row-index">#</th><th>学生姓名</th><th>提交时间</th><th>状态</th><th>操作</th></tr></thead><tbody>{rows.map((row, index) => <tr key={row.id}>
    <td className="cq-row-index">{String(index + 1).padStart(2, '0')}</td>
    <td><div className="cq-student-name"><span className="cq-avatar">{row.display_name.slice(0, 1)}</span><strong>{row.display_name}</strong></div></td>
    <td><time>{new Date(row.submitted_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}</time></td>
    <td><span className="cq-submitted-status">✓ 已提交</span></td>
    <td><Button variant="unstyled" type="button" className="cq-table-action" disabled={busy} onClick={() => onView(row.id)}>查看答卷<span aria-hidden="true"> ↗</span></Button></td>
  </tr>)}</tbody></DataTable>{!rows.length && <EmptyState className="cq-table-empty">{filtered ? '没有找到这位学生' : '等待学生提交答卷'}</EmptyState>}</div>;
}
