import type { LinkedStudent, StudentAssignment } from '../api/student'

/** Recheck the current account's authorized assignment; the QR only supplies its number. */
export function resolvePrintableAssignment(students: LinkedStudent[], assignments: StudentAssignment[], requested: string) {
  if (!/^[1-9]\d*$/.test(requested) || !Number.isSafeInteger(Number(requested))) {
    throw Error('作业链接无效，请返回电脑重新扫码。')
  }
  const active = students.filter(item => item.status === 'active')
  const ids = new Set(active.map(item => item.student_id))
  if (ids.size !== 1) throw Error(ids.size ? '账号关联了多个学生，请联系老师核对绑定。' : '当前账号尚未绑定学生，请先完成班级关联。')
  const student = active[0]!
  if (!Number.isSafeInteger(student.student_id) || student.student_id <= 0) throw Error('学生绑定信息暂不可用，请稍后重试。')
  const matches = assignments.filter(item => item.id === Number(requested))
  if (matches.length !== 1) throw Error('当前账号没有这份作业，请核对电脑与手机的账号绑定。')
  const assignment = matches[0]!
  if (assignment.student_id != null && assignment.student_id !== student.student_id) {
    throw Error('作业归属信息不一致，请联系老师核对。')
  }
  if (!student.classes.some(item => item.class_id === assignment.class_id && item.status === 'active')) {
    throw Error('这份作业的班级关联尚未生效，请联系老师核对。')
  }
  if (assignment.status !== 'published') throw Error('这份作业尚未正式发布，请等待老师发布后重新扫码。')
  if (assignment.assignment_mode !== 'uniform_mixed') throw Error('这份作业暂不提供正式原卷，请联系老师。')
  // Submission and review are separate from the availability of the published paper.
  return { student, assignment }
}

export type PaperPreviewKind = 'pdf' | 'image' | 'download'
export async function detectPaperBlob(blob: Blob, format: string): Promise<PaperPreviewKind> {
  if (!(blob instanceof Blob) || !blob.size) throw Error('试卷文件为空，请稍后重试或联系老师。')
  const extension = format.toLowerCase().replace(/^\./, '')
  const mime = blob.type.split(';')[0]!.trim().toLowerCase()
  const header = new Uint8Array(await blob.slice(0, 8).arrayBuffer())
  if (extension === 'pdf' && mime === 'application/pdf' && [37, 80, 68, 70, 45].every((n, i) => header[i] === n)) return 'pdf'
  if (extension === 'png' && mime === 'image/png' && [137, 80, 78, 71, 13, 10, 26, 10].every((n, i) => header[i] === n)) return 'image'
  if (['jpg', 'jpeg'].includes(extension) && mime === 'image/jpeg' && header[0] === 255 && header[1] === 216 && header[2] === 255) return 'image'
  return 'download'
}

export function safePaperFilename(title: string, format: string): string {
  const name = title.replace(/[<>:"/\\|?*\u0000-\u001f\u007f\u202a-\u202e\u2066-\u2069]/g, '_').replace(/^\.+|[. ]+$/g, '').slice(0, 80).trim() || '正式作业试卷'
  const extension = format.toLowerCase().replace(/^\./, '')
  return `${name}.${/^(pdf|png|jpe?g|docx?|xlsx?|pptx?|txt|rtf|odt)$/.test(extension) ? extension : 'bin'}`
}

export interface PaperDocument { url: string; kind: PaperPreviewKind; filename: string }
/** A retry or unmount invalidates late responses and releases every owned object URL. */
export function createPaperDocumentLoader(urls: Pick<typeof URL, 'createObjectURL' | 'revokeObjectURL'> = URL) {
  let serial = 0
  let current: string | null = null
  let disposed = false
  function clear() {
    serial++
    if (current) urls.revokeObjectURL(current)
    current = null
  }
  return {
    clear,
    dispose() { disposed = true; clear() },
    async load(fetchBlob: () => Promise<Blob>, format: string, title: string): Promise<PaperDocument | null> {
      if (disposed) return null
      clear()
      const request = serial
      try {
        const blob = await fetchBlob()
        if (disposed || request !== serial) return null
        const kind = await detectPaperBlob(blob, format)
        if (disposed || request !== serial) return null
        // Unknown/active formats are offered only as attachment downloads.
        current = urls.createObjectURL(kind === 'download' ? new Blob([blob], { type: 'application/octet-stream' }) : blob)
        return { url: current, kind, filename: safePaperFilename(title, format) }
      } catch (error) {
        if (disposed || request !== serial) return null
        throw error
      }
    },
  }
}
