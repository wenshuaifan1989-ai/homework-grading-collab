import type { StudentAssignment } from '../api/student'

export type AssignmentFilter = 'all' | 'todo' | 'processing' | 'review' | 'completed' | 'attention'
export const assignmentFilters: Array<{ value: AssignmentFilter; label: string }> = [
  { value: 'all', label: '全部作业' }, { value: 'todo', label: '待提交' },
  { value: 'processing', label: '处理中' }, { value: 'review', label: '待复核' },
  { value: 'completed', label: '已完成' }, { value: 'attention', label: '需处理' },
]
export function subjectLabel(code?: string | null): string {
  const names: Record<string, string> = { math: '数学', chinese: '语文', english: '英语', physics: '物理', chemistry: '化学', biology: '生物', history: '历史', geography: '地理' }
  return code ? names[code] || code : '未标学科'
}
export function gradeLabel(code?: string | null): string {
  const names: Record<string, string> = { grade7: '初一', grade8: '初二', grade9: '初三' }
  if (!code) return ''
  return names[code] || (/^grade[1-6]$/.test(code) ? `${['一', '二', '三', '四', '五', '六'][Number(code.slice(5)) - 1]}年级` : code)
}
export function isReview(status?: string | null): boolean {
  return ['WAIT_REVIEW', 'HOLD_REVIEW'].includes((status || '').toUpperCase())
}
export function assignmentGroup(item: StudentAssignment): Exclude<AssignmentFilter, 'all'> {
  if (isReview(item.task_status)) return 'review'
  if (!item.submitted && !item.task_id) return 'todo'
  if (item.task_status === 'SUCCESS') return 'completed'
  if (['FAILED', 'CANCELLED', 'UNKNOWN_LAYOUT'].includes(item.task_status || '')) return 'attention'
  return 'processing'
}
export function taskLabel(status?: string | null): string {
  const labels: Record<string, string> = { SUCCESS: '批改已完成', WAIT_REVIEW: '等待老师复核', HOLD_REVIEW: '等待老师复核', PENDING: '已提交，排队中', PREPROCESSING: '正在处理照片', PROCESSING: '正在处理', GRADING: '正在批改', FAILED: '处理未完成', CANCELLED: '已取消', UNKNOWN_LAYOUT: '需核对试卷与照片' }
  return status ? labels[status] || '状态待确认' : '待提交'
}
// An unzoned server timestamp is displayed, but never used to assert overdue.
export function deadlineTimestamp(value?: string | null): number | null {
  if (!value || !/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value)) return null
  const stamp = Date.parse(value)
  return Number.isFinite(stamp) ? stamp : null
}
export function deadlineHint(value: string | null | undefined, now: number): string {
  const deadline = deadlineTimestamp(value)
  if (deadline === null || !Number.isFinite(now)) return ''
  if (deadline < now) return '已过截止'
  const dayNumber = (stamp: number) => {
    const parts = new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Shanghai', year: 'numeric', month: 'numeric', day: 'numeric' }).formatToParts(new Date(stamp))
    const part = (type: string) => Number(parts.find(item => item.type === type)!.value)
    return Date.UTC(part('year'), part('month') - 1, part('day')) / 86400000
  }
  const days = dayNumber(deadline) - dayNumber(now)
  return days === 0 ? '今天截止' : days === 1 ? '明天截止' : ''
}
export function dateLabel(value?: string | null): string {
  if (!value) return '未设置截止时间'
  const stamp = deadlineTimestamp(value)
  if (stamp !== null) return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(stamp))
  return value.replace('T', ' ').replace(/\.\d+$/, '')
}
export function sortAssignments(items: StudentAssignment[]): StudentAssignment[] {
  const order = { todo: 0, attention: 1, review: 2, processing: 3, completed: 4 }
  return [...items].sort((a, b) => order[assignmentGroup(a)] - order[assignmentGroup(b)] || (deadlineTimestamp(a.due_at) ?? Infinity) - (deadlineTimestamp(b.due_at) ?? Infinity))
}
// Reminder groups use only deadlines that carry an explicit timezone. A missing
// or unzoned deadline remains visible on its assignment without invented urgency.
export function assignmentReminders(items: StudentAssignment[], now: number) {
  const pending = items.filter(item => assignmentGroup(item) === 'todo')
  const byDeadline = (a: StudentAssignment, b: StudentAssignment) => (deadlineTimestamp(a.due_at) ?? Infinity) - (deadlineTimestamp(b.due_at) ?? Infinity)
  return {
    attention: items.filter(item => assignmentGroup(item) === 'attention' || (assignmentGroup(item) === 'todo' && (deadlineTimestamp(item.due_at) ?? Infinity) < now)).sort(byDeadline),
    upcoming: pending.filter(item => { const deadline = deadlineTimestamp(item.due_at); return deadline !== null && deadline >= now }).sort(byDeadline),
    review: items.filter(item => assignmentGroup(item) === 'review').sort(byDeadline),
  }
}
export function questionLabel(result?: string | null): string {
  return ({ correct: '正确', partial: '部分正确，需订正', wrong: '需订正' } as Record<string, string>)[result || ''] || '等待老师核对'
}
export function trustedQuestion(row?: { result?: string | null; score?: number | null; max_score?: number | null } | null): boolean {
  return !!row && ['correct', 'partial', 'wrong'].includes(row.result || '') && typeof row.score === 'number' && Number.isFinite(row.score) && typeof row.max_score === 'number' && Number.isFinite(row.max_score)
}
export function trustedSummary(result: { results?: Array<{ result?: string; score?: number; max_score?: number }>; total_score?: number; total_max_score?: number }): boolean {
  return !!result.results?.length && result.results.every(trustedQuestion) && typeof result.total_score === 'number' && Number.isFinite(result.total_score) && typeof result.total_max_score === 'number' && Number.isFinite(result.total_max_score)
}
export function mistakeLabel(status?: string): string {
  const labels: Record<string, string> = { open: '待订正', pending: '待处理', correction_submitted: '订正待老师审核', mastered_self_reported: '已自评掌握', mastered: '老师已审核', not_wrong: '已核对为非错题', submitted: '待老师审核', self_reported_mastered: '已自评掌握', accepted: '老师已认可', retry_requested: '请继续订正' }
  return labels[status || ''] || '状态待确认'
}
