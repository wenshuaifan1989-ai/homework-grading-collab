import type { LinkedStudent } from '../api/student'
import type { MistakeItem } from '../api/paper'
import type { PhonePrintProvider } from './phonePrint'
import type { MobileEntryProvider } from './mobileEntry'

// Optional student-only integration. No proposed endpoint is called until its contract is approved.
export interface StudentIdentityDetails {
  student_id: number
  school_name: string | null
  class_id: number
  class_name: string
  student_no: string | null
  student_sequence: string | null
}
export interface StudentRelative {
  relationship_type: string
  masked_phone: string | null
  is_current: boolean
}
export interface MistakeChangeReceipt {
  id: number
  student_id: number
  deleted: boolean
}
// Supplied only by a confirmed student-facing adapter. Existing question/analysis
// responses are not evidence that a standard answer has been released.
export interface StudentMistakeMaterial {
  student_id: number
  mistake_id: number
  question: {
    text: string
    options: string[] | Record<string, string> | null
    complete: boolean
    image_data_url?: string | null
  }
  standard_answer: { released: boolean; text: string | null }
  student_answer?: string | null
}
export interface StudentExperienceIntegration {
  identity?: (studentId: number) => Promise<StudentIdentityDetails>
  relatives?: (studentId: number) => Promise<StudentRelative[]>
  deletedMistakes?: (studentId: number) => Promise<MistakeItem[]>
  changeMistake?: (studentId: number, mistakeId: number, deleted: boolean, key: string) => Promise<MistakeChangeReceipt>
  phonePrint?: PhonePrintProvider
  mobileEntry?: MobileEntryProvider
  mistakeMaterial?: (studentId: number, mistakeId: number) => Promise<StudentMistakeMaterial>
}
export const studentExperience: StudentExperienceIntegration = {}

export function singleStudent(students: LinkedStudent[]): LinkedStudent | null {
  const active = students.filter(item => item.status === 'active')
  const ids = new Set(active.map(item => item.student_id))
  return ids.size === 1 ? active[0] : null
}
export function identityIssue(students: LinkedStudent[]): string {
  return new Set(students.filter(item => item.status === 'active').map(item => item.student_id)).size > 1
    ? '当前账号关联了多个学生，与一号一生规则不一致。请联系老师核对绑定后重试。'
    : '当前账号尚未绑定学生，请先完成班级关联。'
}
export function mistakeSubject(item: MistakeItem): string {
  return item.subject?.trim() || '__unconfirmed__'
}
export function orderedSubjects(items: MistakeItem[]): string[] {
  const order = ['chinese', 'math', 'english']
  return [...new Set(items.map(mistakeSubject))].sort((a, b) => {
    const ai = order.indexOf(a), bi = order.indexOf(b)
    return (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi) || a.localeCompare(b, 'zh-CN')
  })
}
export function assignmentMistakes(items: MistakeItem[], subject: string) {
  const groups = new Map<string, { key: string; assignmentId: number | null; title: string; items: MistakeItem[] }>()
  // An empty selection never means "all subjects" in the mistake library.
  for (const item of items.filter(item => !!subject && mistakeSubject(item) === subject)) {
    const known = Number.isInteger(item.assignment_id) && item.assignment_id > 0
    const key = known ? `assignment-${item.assignment_id}` : `unconfirmed-${item.id}`
    let group = groups.get(key)
    if (!group) {
      group = { key, assignmentId: known ? item.assignment_id : null, title: item.assignment_title?.trim() || '作业名称待核对', items: [] }
      groups.set(key, group)
    }
    group.items.push(item)
  }
  return [...groups.values()]
}
export function validMistakeReceipt(receipt: MistakeChangeReceipt, studentId: number, id: number, deleted: boolean): boolean {
  return receipt?.id === id && receipt.student_id === studentId && receipt.deleted === deleted
}
