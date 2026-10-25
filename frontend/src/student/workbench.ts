import type { StudentAssignment } from '../api/student'

export type AssignmentFilter = 'todo' | 'submitted' | 'review'
export const assignmentFilters: Array<{ value: AssignmentFilter; label: string }> = [
  { value: 'todo', label: '待提交' }, { value: 'submitted', label: '已提交' },
  { value: 'review', label: '待复核' },
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
export function assignmentGroup(item: StudentAssignment): AssignmentFilter {
  if (isReview(item.task_status)) return 'review'
  if (!item.submitted && !item.task_id) return 'todo'
  return 'submitted'
}
export function assignmentGroupLabel(item: StudentAssignment): string {
  return assignmentFilters.find(filter => filter.value === assignmentGroup(item))!.label
}
export function taskLabel(status?: string | null): string {
  const labels: Record<string, string> = { SUCCESS: '已收到批改状态，请查看反馈', WAIT_REVIEW: '等待老师复核', HOLD_REVIEW: '等待老师复核', PENDING: '老师加紧批改中', PREPROCESSING: '老师加紧批改中', PROCESSING: '老师加紧批改中', GRADING: '老师加紧批改中', FAILED: '本次处理未完成，请联系老师核对原任务', CANCELLED: '本次任务已取消，请联系老师核对', UNKNOWN_LAYOUT: '试卷与照片需核对，请联系老师核对原任务' }
  return status ? labels[status] || '状态待确认' : '待提交'
}
export function assignmentDetail(item: StudentAssignment, feedbackVerified = false): string {
  if (assignmentGroup(item) === 'todo') return ''
  if (item.task_status === 'SUCCESS') return feedbackVerified ? '题目反馈已核对，可查看批改反馈。' : '已收到处理结果状态，请查看反馈。'
  if (item.task_status === 'RESULT_PENDING') return '老师加紧批改中，反馈尚待确认。'
  return item.task_status ? taskLabel(item.task_status) : '提交已收到，状态待确认。'
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
  return assignmentFilters.flatMap(({ value }) => {
    const group = items.filter(item => assignmentGroup(item) === value)
    const time = (item: StudentAssignment) => deadlineTimestamp(value === 'todo' ? item.due_at : item.submitted_at)
    const dated = group.filter(item => time(item) !== null).sort((a, b) => (time(a)! - time(b)!) * (value === 'submitted' ? -1 : 1))
    let index = 0
    // Missing/ambiguous dates keep their original slots instead of gaining an invented priority.
    return group.map(item => time(item) === null ? item : dated[index++]!)
  })
}
// Reminder groups use only deadlines that carry an explicit timezone. A missing
// or unzoned deadline remains visible on its assignment without invented urgency.
export function assignmentReminders(items: StudentAssignment[], now: number) {
  const pending = items.filter(item => assignmentGroup(item) === 'todo')
  const byDeadline = (a: StudentAssignment, b: StudentAssignment) => (deadlineTimestamp(a.due_at) ?? Infinity) - (deadlineTimestamp(b.due_at) ?? Infinity)
  return {
    overdue: pending.filter(item => (deadlineTimestamp(item.due_at) ?? Infinity) < now).sort(byDeadline),
    upcoming: pending.filter(item => { const deadline = deadlineTimestamp(item.due_at); return deadline !== null && deadline >= now }).sort(byDeadline),
    review: sortAssignments(items.filter(item => assignmentGroup(item) === 'review')),
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
