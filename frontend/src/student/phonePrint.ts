export interface PhonePrintContext { student_id: number; assignment_id: number }
export interface PhonePrintLink extends PhonePrintContext {
  purpose: 'print'
  phone_url: string
  qr_image: string
}
export interface PhonePrintProvider {
  createLink: (studentId: number, assignmentId: number) => Promise<PhonePrintLink>
}
export interface PhonePrintState {
  phase: 'loading' | 'ready' | 'error' | 'unavailable'
  link: PhonePrintLink | null
  busy: boolean
  error: string
}
export function validPrintLink(value: unknown, context: PhonePrintContext): value is PhonePrintLink {
  if (!value || typeof value !== 'object') return false
  const link = value as PhonePrintLink
  if (link.student_id !== context.student_id || link.assignment_id !== context.assignment_id
    || link.purpose !== 'print' || typeof link.phone_url !== 'string' || typeof link.qr_image !== 'string') return false
  try {
    const url = new URL(link.phone_url)
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return false
  } catch { return false }
  const prefix = 'data:image/png;base64,'
  const encoded = link.qr_image.slice(prefix.length)
  return link.qr_image.startsWith(prefix) && encoded.length % 4 === 0
    && /^iVBORw0KGgo[A-Za-z0-9+/]*={0,2}$/.test(encoded)
}

// Preparing a print link never queries or creates a homework submission.
export function createPhonePrintSession(
  provider: PhonePrintProvider | undefined,
  context: PhonePrintContext,
  onState: (state: PhonePrintState) => void,
) {
  let active = true, generation = 0, busy = false
  function publish(state: PhonePrintState) { if (active) onState(state) }
  async function start() {
    if (!active || busy) return
    if (![context.student_id, context.assignment_id].every(id => Number.isInteger(id) && id > 0)) {
      publish({ phase: 'error', link: null, busy: false, error: '无法确认当前学生与作业，请返回作业列表重新打开。' })
      return
    }
    if (!provider) {
      publish({ phase: 'unavailable', link: null, busy: false, error: '手机扫码打印尚未接通，可以先在电脑打开或下载已发布的试卷。' })
      return
    }
    const request = ++generation
    busy = true
    publish({ phase: 'loading', link: null, busy: true, error: '' })
    try {
      const link = await provider.createLink(context.student_id, context.assignment_id)
      if (!active || request !== generation) return
      if (!validPrintLink(link, context)) throw Error('invalid print link')
      publish({ phase: 'ready', link, busy: false, error: '' })
    } catch {
      if (active && request === generation) {
        publish({ phase: 'error', link: null, busy: false, error: '打印二维码暂时无法准备，请重试。' })
      }
    } finally { if (active && request === generation) busy = false }
  }
  function stop() { active = false; generation++ }
  return { start, stop }
}
