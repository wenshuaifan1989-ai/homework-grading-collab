import type { MistakeItem } from '../api/paper'
import type { StudentMistakeMaterial } from './experience'

export interface MistakePrintSelection {
  item: MistakeItem
  material: StudentMistakeMaterial | null
}
export interface MistakePrintEntry {
  number: number
  id: number
  assignmentTitle: string
  questionNo: string
  text: string
  options: string[]
  imageDataUrl: string | null
  answer: string
}
export interface MistakePrintPreparation {
  subject: string
  entries: MistakePrintEntry[]
  issues: Array<{ id: number; message: string }>
}
export type MistakePrintLayout = 'filled' | 'split'

function positiveId(value: number): boolean {
  return Number.isSafeInteger(value) && value > 0
}
function text(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}
function optionLines(options: StudentMistakeMaterial['question']['options']): string[] | null {
  if (options === null) return []
  if (Array.isArray(options)) return options.every(value => typeof value === 'string' && value.trim()) ? options.map(value => value.trim()) : null
  if (!options || typeof options !== 'object') return null
  const pairs = Object.entries(options)
  if (!pairs.every(([key, value]) => key.trim() && typeof value === 'string' && value.trim())) return null
  return pairs.map(([key, value]) => `${key.trim()} ${value.trim()}`)
}

// Only a clean image explicitly supplied with the student material is eligible.
// Never fetch crop_url/original_url: those images may contain handwriting.
export function validMistakeImage(value: unknown): value is string {
  if (typeof value !== 'string' || value.length > 16 * 1024 * 1024) return false
  const match = /^data:image\/(png|jpeg);base64,([A-Za-z0-9+/]+={0,2})$/.exec(value)
  if (!match || match[2]!.length % 4) return false
  try {
    const bytes = atob(match[2]!)
    const signature = match[1] === 'png' ? [137, 80, 78, 71, 13, 10, 26, 10] : [255, 216, 255]
    return signature.every((byte, index) => bytes.charCodeAt(index) === byte)
  } catch { return false }
}
export function safeQuestionImage(value?: string | null): string | null {
  return validMistakeImage(value) ? value : null
}

export function prepareMistakePrint(studentId: number, subject: string, selection: MistakePrintSelection[]): MistakePrintPreparation {
  const result: MistakePrintPreparation = { subject, entries: [], issues: [] }
  if (!positiveId(studentId) || !text(subject) || subject === '__unconfirmed__') {
    result.issues.push({ id: 0, message: '学生或学科信息待核对，请返回错题库重新选择。' })
    return result
  }
  if (!selection.length) {
    result.issues.push({ id: 0, message: '请先选择要下载或打印的题目。' })
    return result
  }
  const seen = new Set<number>()
  for (const { item, material } of selection) {
    const issue = (message: string) => result.issues.push({ id: item.id, message })
    if (!positiveId(item.id) || item.student_id !== studentId || text(item.subject) !== subject || seen.has(item.id)) {
      issue('题目归属或学科不一致，请返回重新选择。')
      continue
    }
    seen.add(item.id)
    if (!material || material.student_id !== studentId || material.mistake_id !== item.id) {
      issue('尚未取得这道题的可公开题面和标准答案。')
      continue
    }
    const question = material.question
    const options = question ? optionLines(question.options) : null
    if (!question || question.complete !== true || !text(question.text) || options === null) {
      issue('完整题面尚未确认，暂不能打印。')
      continue
    }
    if (question.image_data_url != null && !validMistakeImage(question.image_data_url)) {
      issue('题图不可用，需要确认干净题图后再打印。')
      continue
    }
    if (material.standard_answer?.released !== true || !text(material.standard_answer.text)) {
      issue('老师尚未公开完整标准答案，暂不能打印。')
      continue
    }
    result.entries.push({
      number: result.entries.length + 1,
      id: item.id,
      assignmentTitle: text(item.assignment_title) || '作业名称待核对',
      questionNo: text(item.question_no) || '未提供',
      text: text(question.text),
      options,
      imageDataUrl: question.image_data_url || null,
      answer: text(material.standard_answer.text),
    })
  }
  return result
}

const printStyles = `
@page{size:A4 portrait;margin:18mm 16mm}
*{box-sizing:border-box}html,body{margin:0;padding:0;background:white;color:#17231d}
body{font-family:Arial,"Microsoft YaHei",sans-serif;font-size:12pt;line-height:1.7}
h1{font-size:19pt;margin:0 0 5mm}h2{font-size:17pt;margin:0 0 7mm}
.meta{font-size:10pt;color:#526159;margin:0 0 7mm}.question{margin:0 0 9mm;break-inside:avoid;page-break-inside:avoid}
.source{font-size:10pt;color:#526159;margin:0 0 2mm}.stem,.answer,.option{white-space:pre-wrap;overflow-wrap:anywhere;margin:0 0 2mm}
.number{font-weight:bold}.question img{display:block;max-width:100%;max-height:225mm;object-fit:contain;margin:4mm 0}
.options{margin:2mm 0 4mm}.answer{margin-top:5mm}.answer-label{font-weight:bold}
.answers{break-before:page;page-break-before:always}.answer-entry{break-inside:avoid;page-break-inside:avoid;margin-bottom:7mm}
.writing-space{height:24mm}
`
const subjectNames: Record<string, string> = { chinese: '语文', math: '数学', english: '英语', physics: '物理', chemistry: '化学', biology: '生物', history: '历史', geography: '地理' }
function subjectTitle(code: string): string { return subjectNames[code] || code }

// Student material is inserted exclusively through textContent and DOM setters.
// The isolated document carries no student identity, responses, analysis or scores.
export function buildMistakePrintDocument(doc: Document, prepared: MistakePrintPreparation, layout: MistakePrintLayout): void {
  if (prepared.issues.length || !prepared.entries.length) throw Error('请先处理所选题目的打印问题。')
  if (layout !== 'filled' && layout !== 'split') throw Error('打印版式不可用。')
  const append = (parent: Node, tag: string, content = '', className = '') => {
    const node = doc.createElement(tag)
    node.textContent = content
    if (className) node.className = className
    parent.appendChild(node)
    return node
  }
  const style = doc.createElement('style')
  style.textContent = printStyles
  doc.head.appendChild(style)
  doc.documentElement.lang = 'zh-CN'
  doc.title = `${subjectTitle(prepared.subject)}错题练习`
  doc.body.replaceChildren()
  const main = append(doc.body, 'main')
  append(main, 'h1', `${subjectTitle(prepared.subject)}错题练习`)
  append(main, 'p', `${prepared.entries.length} 题 · ${layout === 'filled' ? '答案填充版' : '试题答案拆分版'}`, 'meta')
  for (const entry of prepared.entries) {
    const question = append(main, 'section', '', 'question')
    append(question, 'p', `${entry.assignmentTitle} · 原题号 ${entry.questionNo}`, 'source')
    append(question, 'p', `${entry.number}. ${entry.text}`, 'stem')
    if (entry.options.length) {
      const options = append(question, 'div', '', 'options')
      for (const option of entry.options) append(options, 'p', option, 'option')
    }
    if (entry.imageDataUrl) {
      // Recheck at the only output boundary even if an external caller constructs entries.
      if (!validMistakeImage(entry.imageDataUrl)) throw Error('题图不可用，请重新选择。')
      const image = doc.createElement('img')
      image.src = entry.imageDataUrl
      image.alt = `第 ${entry.number} 题题图`
      question.appendChild(image)
    }
    if (layout === 'filled') {
      append(question, 'p', '标准答案', 'answer-label')
      append(question, 'p', entry.answer, 'answer')
    } else append(question, 'div', '', 'writing-space')
  }
  if (layout === 'split') {
    const answers = append(main, 'section', '', 'answers')
    append(answers, 'h2', `${subjectTitle(prepared.subject)}错题参考答案`)
    for (const entry of prepared.entries) {
      const answer = append(answers, 'section', '', 'answer-entry')
      append(answer, 'p', `${entry.number}. ${entry.assignmentTitle} · 原题号 ${entry.questionNo}`, 'source')
      append(answer, 'p', entry.answer, 'answer')
    }
  }
}

const frameSkeleton = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'"><title>错题打印</title></head><body></body></html>'
function abortedError(): Error { return Object.assign(Error('打印准备已取消'), { name: 'AbortError' }) }
function waitForEvent(target: EventTarget, readyEvent: string, signal: AbortSignal, timeout: number): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(abortedError()); return }
    let timer: ReturnType<typeof setTimeout>
    const cleanup = () => {
      clearTimeout(timer)
      target.removeEventListener(readyEvent, loaded)
      target.removeEventListener('error', failed)
      signal.removeEventListener('abort', cancelled)
    }
    const loaded = () => { cleanup(); resolve() }
    const failed = () => { cleanup(); reject(Error('打印文档或题图未能加载，请重试。')) }
    const cancelled = () => { cleanup(); reject(abortedError()) }
    target.addEventListener(readyEvent, loaded, { once: true })
    target.addEventListener('error', failed, { once: true })
    signal.addEventListener('abort', cancelled, { once: true })
    timer = setTimeout(failed, timeout)
  })
}
function waitForPromise(promise: PromiseLike<unknown>, signal: AbortSignal, timeout: number): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(abortedError()); return }
    const done = (error?: unknown) => { clearTimeout(timer); signal.removeEventListener('abort', cancelled); error ? reject(error) : resolve() }
    const cancelled = () => done(abortedError())
    const timer = setTimeout(() => done(Error('打印文档准备超时，请重试。')), timeout)
    signal.addEventListener('abort', cancelled, { once: true })
    Promise.resolve(promise).then(() => done(), done)
  })
}
export interface MistakePrintJobOptions {
  onBusyChange?: (busy: boolean) => void
  readyTimeout?: number
  cleanupTimeout?: number
}
export function createMistakePrintJob(host: Document, options: MistakePrintJobOptions = {}) {
  interface Job { frame: HTMLIFrameElement; abort: AbortController; timer: ReturnType<typeof setTimeout> | null; afterPrint: (() => void) | null }
  let active: Job | null = null
  let disposed = false
  const finish = (job: Job) => {
    if (job.timer) clearTimeout(job.timer)
    if (job.afterPrint) job.frame.contentWindow?.removeEventListener('afterprint', job.afterPrint)
    job.abort.abort()
    job.frame.remove()
    if (active === job) { active = null; options.onBusyChange?.(false) }
  }
  return {
    get busy() { return !!active },
    cancel() { if (active) finish(active) },
    dispose() { disposed = true; if (active) finish(active) },
    async print(prepared: MistakePrintPreparation, layout: MistakePrintLayout): Promise<'opened' | 'cancelled' | 'ignored'> {
      if (disposed || active) return 'ignored'
      if (prepared.issues.length || !prepared.entries.length) throw Error('请先处理所选题目的打印问题。')
      const frame = host.createElement('iframe')
      frame.title = '错题打印文档'
      frame.setAttribute('aria-hidden', 'true')
      frame.setAttribute('sandbox', 'allow-same-origin allow-modals')
      frame.style.cssText = 'position:fixed;left:0;bottom:0;width:1px;height:1px;opacity:0;pointer-events:none;border:0'
      const job: Job = { frame, abort: new AbortController(), timer: null, afterPrint: null }
      active = job
      options.onBusyChange?.(true)
      const readyTimeout = options.readyTimeout ?? 15000
      try {
        const loaded = waitForEvent(frame, 'load', job.abort.signal, readyTimeout)
        frame.srcdoc = frameSkeleton
        host.body.appendChild(frame)
        await loaded
        if (active !== job) return 'cancelled'
        const document = frame.contentDocument
        const view = frame.contentWindow
        if (!document?.body || !view || typeof view.print !== 'function') throw Error('当前浏览器无法打开打印文档，请更换浏览器后重试。')
        buildMistakePrintDocument(document, prepared, layout)
        const images = Array.from(document.images).map(async image => {
          if (!image.complete) await waitForEvent(image, 'load', job.abort.signal, readyTimeout)
          if (!image.naturalWidth) throw Error('题图尚未完整加载，请重试。')
        })
        await Promise.all(images)
        if (document.fonts?.ready) await waitForPromise(document.fonts.ready, job.abort.signal, readyTimeout)
        if (active !== job || job.abort.signal.aborted) return 'cancelled'
        job.afterPrint = () => finish(job)
        view.addEventListener('afterprint', job.afterPrint, { once: true })
        view.focus()
        view.print()
        // Some browsers omit afterprint. Keep the document alive during their
        // dialog, while bounding its lifetime and allowing explicit close.
        if (active === job) job.timer = setTimeout(() => finish(job), options.cleanupTimeout ?? 60000)
        return 'opened'
      } catch (error) {
        const cancelled = job.abort.signal.aborted || active !== job
        finish(job)
        if (cancelled) return 'cancelled'
        throw error
      }
    },
  }
}
