export interface MobileEntryLink {
  student_id: number
  scope: 'student-workspace'
  phone_url: string
  qr_image: string
}
export interface MobileEntryProvider {
  createLink: (studentId: number) => Promise<MobileEntryLink>
}
export interface MobileEntryState {
  phase: 'loading' | 'ready' | 'error' | 'unavailable'
  link: MobileEntryLink | null
  busy: boolean
  error: string
}

export function validMobileEntryLink(value: unknown, studentId: number): value is MobileEntryLink {
  if (!Number.isSafeInteger(studentId) || studentId <= 0 || !value || typeof value !== 'object') return false
  const link = value as MobileEntryLink
  if (link.student_id !== studentId || link.scope !== 'student-workspace'
    || typeof link.phone_url !== 'string' || typeof link.qr_image !== 'string') return false
  try {
    const url = new URL(link.phone_url)
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return false
  } catch { return false }
  const prefix = 'data:image/png;base64,'
  const data = link.qr_image.slice(prefix.length)
  return link.qr_image.startsWith(prefix) && data.length % 4 === 0
    && /^iVBORw0KGgo[A-Za-z0-9+/]*={0,2}$/.test(data)
}

// Opening the mobile site is read-only. There is no submission, assignment query or polling here.
export function createMobileEntrySession(
  provider: MobileEntryProvider | undefined,
  studentId: number,
  onState: (state: MobileEntryState) => void,
) {
  let active = true, generation = 0, busy = false
  let state: MobileEntryState = { phase: 'loading', link: null, busy: false, error: '' }
  function publish(patch: Partial<MobileEntryState>) {
    state = { ...state, ...patch }
    if (active) onState({ ...state, link: state.link ? { ...state.link } : null })
  }
  async function start() {
    if (!active || busy || state.link) return
    if (!provider || !Number.isSafeInteger(studentId) || studentId <= 0) {
      publish({ phase: 'unavailable', busy: false, error: '手机端入口尚未接通，请稍后重试。' })
      return
    }
    const request = ++generation
    busy = true
    publish({ phase: 'loading', busy: true, error: '' })
    try {
      const link = await provider.createLink(studentId)
      if (!active || request !== generation) return
      if (!validMobileEntryLink(link, studentId)) throw Error('Invalid mobile entry')
      publish({ phase: 'ready', link: { ...link }, busy: false })
    } catch {
      if (active && request === generation) publish({ phase: 'error', busy: false, error: '暂时无法读取手机端入口，请重试。' })
    } finally { if (active && request === generation) busy = false }
  }
  function stop() { active = false; generation++ }
  return { start, stop }
}
