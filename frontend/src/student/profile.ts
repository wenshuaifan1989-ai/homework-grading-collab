import type { LinkedStudent, StudentBinding } from '../api/student'

export type ProfileBindingState = 'idle' | 'loading' | 'ready' | 'error' | 'not_applicable'
export interface ProfileMetric { label: string; value: number | null; unit: '份' | '题' }

export function maskedPhone(value?: string | null): string {
  const text = value?.trim()
  if (!text) return '当前资料未提供'
  const digits = text.replace(/\D/g, '')
  return digits.length >= 10 ? `${digits.slice(0, 3)}****${digits.slice(-4)}` : digits.length >= 7 ? `${digits[0]}****${digits.slice(-2)}` : '已提供（已隐藏）'
}
export function maskedEmail(value?: string | null): string {
  const text = value?.trim()
  if (!text) return '当前资料未提供'
  const parts = text.split('@')
  return parts.length === 2 && parts[0] && parts[1] ? `${parts[0][0]}***@${parts[1]}` : '已提供（已隐藏）'
}
export function accountName(value?: string | null): string {
  if (!value?.trim()) return '当前资料未提供'
  if (value.includes('@')) return maskedEmail(value)
  return /^\+?[\d\s()-]{7,}$/.test(value.trim()) ? maskedPhone(value) : value.trim()
}
export function relationshipLabel(student?: LinkedStudent | null): string {
  if (!student) return '尚未选择学习身份'
  const names: Record<string, string> = { self: '本人', father: '父亲', mother: '母亲', guardian: '监护人', paternal_grandfather: '祖父', paternal_grandmother: '祖母', maternal_grandfather: '外祖父', maternal_grandmother: '外祖母', other: '家庭成员' }
  return student.relationship_label?.trim() || names[student.relationship_type] || '关联关系待确认'
}
export function profileBinding(student: LinkedStudent | null | undefined, binding: StudentBinding | null, state: ProfileBindingState) {
  const empty = { studentNo: null as string | null, className: null as string | null }
  if (!student) return { ...empty, message: '请先在工作台选择学习身份。' }
  if (state === 'loading' || state === 'idle') return { ...empty, message: '正在核对当前身份的绑定资料…' }
  if (state === 'error') return { ...empty, message: '绑定资料暂时无法读取，请重试。' }
  if (state === 'not_applicable') return { ...empty, message: '当前通过关联关系访问学生资料。' }
  if (!binding || typeof binding.is_bound !== 'boolean') return { ...empty, message: '绑定资料尚未确认，请重试。' }
  if (!binding.is_bound) return { ...empty, message: '当前账户尚未完成班级身份绑定。' }
  if (binding.student_id !== student.student_id) return { ...empty, message: '绑定资料与当前选择的学生不一致，请联系老师核对。' }
  const classroom = (student.classes || []).find(item => item.class_id === binding.class_id && item.status === 'active')
  if (!classroom) return { ...empty, message: '当前绑定班级资料待核对。' }
  return { studentNo: binding.student_no?.trim() || null, className: classroom.class_name, message: '已核对当前学生的班级绑定。' }
}
