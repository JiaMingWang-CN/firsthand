import { reactive } from 'vue'
import { personas, steps, findings, posts, reads, withheld, flows, timeline, replaceAll } from './data.js'

export const DAY = 1440
// 与后端 core/runtime.py 的 TEXT_ONLY_NOTE 一致：模型不支持图像识别时，人物浏览只读页面的文字和结构
export const TEXT_ONLY_NOTE = '模型不支持图像识别：人物只能读取页面的文字和结构，看不到布局、图片和样式，本次结果参考性有限'
export const pad = (n) => String(n).padStart(2, '0')

/** 模拟分钟（距运行起点）→ "D1 21:10" */
export function fmt(m) {
  if (m > 0 && m % DAY === 0) return `D${m / DAY} 24:00`
  const day = Math.floor(m / DAY) + 1
  const mm = ((m % DAY) + DAY) % DAY
  return `D${day} ${pad(Math.floor(mm / 60))}:${pad(Math.floor(mm % 60))}`
}
export const hhmm = (m) => fmt(m).slice(3)
export const parseSim = (str) => {
  const r = /^D(\d+)[-\s](\d{2}):(\d{2})$/.exec(str || '')
  return r ? (Number(r[1]) - 1) * DAY + Number(r[2]) * 60 + Number(r[3]) : null
}
export const mmss = (sec) => `${pad(Math.floor(sec / 60))}:${pad(Math.round(sec % 60))}`
/** 当天分钟数 → "09:40" */
export const clockOf = (min) => `${pad(Math.floor(min / 60))}:${pad(min % 60)}`

// 派生容器：加载新运行后由 rebuild() 原地重建，引用不变
export const P = reactive({})
export const F = reactive({})
export const findingById = reactive({})
export const postById = reactive({})
export const socialEvents = reactive([])
export const tasked = reactive([])
export const taskedDone = reactive([])

const refill = (target, entries) => {
  for (const key of Object.keys(target)) delete target[key]
  Object.assign(target, entries)
}

export function rebuild() {
  refill(P, Object.fromEntries(personas.map((p, i) => [p.id, { ...p, index: i }])))
  refill(F, Object.fromEntries(flows.map((f) => [f.id, f])))
  refill(findingById, Object.fromEntries(findings.map((f) => [f.id, f])))
  refill(postById, Object.fromEntries(posts.map((p) => [p.id, p])))
  const events = []
  for (const p of posts) {
    events.push({ kind: 'post', pid: p.author, t: p.t, ref: p.id })
    for (const c of p.comments) events.push({ kind: 'comment', pid: c.author, t: c.t, ref: c.id, post: p.id })
  }
  for (const r of reads) events.push({ kind: 'read', pid: r.pid, t: r.t, ref: r.post })
  replaceAll(socialEvents, events.sort((a, b) => a.t - b.t))
  const assigned = personas.filter((p) => p.assignment !== 'explore')
  tasked.splice(0, tasked.length, ...assigned)
  taskedDone.splice(0, taskedDone.length, ...assigned.filter((p) => p.outcome === 'success'))
}

export const label = {
  device: { mobile: '手机', desktop: '桌面' },
  tech: { novice: '小白', normal: '普通', developer: '开发者' },
  patience: { low: '低耐心', normal: '中耐心', high: '高耐心' },
  participation: { poster: '发帖者', commenter: '评论者', reactor: '点赞者', lurker: '潜水者' },
  sev: { 1: 'S1 致命', 2: 'S2 严重', 3: 'S3 一般', 4: 'S4 轻微' },
  outcome: { success: '已完成', quit: '已放弃', error: '出错' },
  status: { wait: '等待中', browse: '体验中', social: '在社区', done: '已完成', quit: '已放弃', err: '出错' },
  account: { new_visitor: '新访客', free_user: '免费用户', paid_user: '付费用户' },
}
export const assignmentLabel = (p) => (p.assignment === 'explore' || !F[p.assignment] ? '自由探索' : F[p.assignment].name)

// —— 时间与状态 ——
export const browseStart = (pid) => P[pid].slot
export const browseEnd = (pid) => {
  const list = steps[pid]
  return list.length ? list[list.length - 1].t + 1 : P[pid].slot
}

export function statusAt(pid, t) {
  const start = browseStart(pid)
  const end = browseEnd(pid)
  if (t >= start && t < end) return 'browse'
  if (socialEvents.some((e) => e.pid === pid && e.kind !== 'read' && t >= e.t && t < e.t + 6)) return 'social'
  if (socialEvents.some((e) => e.pid === pid && e.kind === 'read' && t >= e.t && t < e.t + 3)) return 'social'
  if (t < start) return 'wait'
  return P[pid].outcome === 'quit' ? 'quit' : P[pid].outcome === 'error' ? 'err' : 'done'
}

/** 当前正在执行的步骤索引（0 基），未开始返回 -1 */
export function stepIndexAt(pid, t) {
  const list = steps[pid]
  let idx = -1
  for (let i = 0; i < list.length; i++) if (list[i].t <= t) idx = i
  return idx
}

/** 录像秒数（按会话创建时间估算）：所引截图的时刻，未指定截图时取该步骤操作前的截图 */
export const videoSec = (pid, stepNo, snapshot) => {
  const st = steps[pid][stepNo - 1]
  return (snapshot && st?.videoAt?.[snapshot]) ?? st?.video ?? 0
}

// —— 证据 ——
const kindLabel = { step: '步骤', video: '录像', shots: '截图', console: 'Console', network: 'Network' }
export function evLabel(ev) {
  if (ev.kind === 'step') return `步骤 #${ev.step}`
  if (ev.kind === 'video') return `录像 ${mmss(videoSec(ev.pid, ev.step, ev.snapshot))}`
  if (ev.kind === 'shots') return `截图 ×${ev.count || 1}`
  if (ev.kind === 'console') return `Console · #${ev.step}`
  if (ev.kind === 'network') return `Network · #${ev.step}`
  return kindLabel[ev.kind]
}
export function resolveEvidence(ev) {
  const p = P[ev.pid]
  const st = steps[ev.pid][ev.step - 1]
  const snapshot = ev.snapshot ?? st.snaps?.before
  return { persona: p, step: st, stepNo: ev.step, total: steps[ev.pid].length, trace: st.trace || [], snapshot, video: videoSec(ev.pid, ev.step, snapshot) }
}
export const evKey = (ev) => `${ev.pid}#${ev.step}`
export function findingsCiting(pid, stepNo) {
  return findings.filter((f) => f.evidence.some((e) => e.pid === pid && e.step === stepNo))
}

// —— 统计 ——
export function flowStats() {
  return flows.map((f) => {
    const ps = personas.filter((p) => p.assignment === f.id)
    return { ...f, people: ps, done: ps.filter((p) => p.outcome === 'success') }
  })
}

export function npsOf(list) {
  if (!list.length) return { score: null, promoters: 0, detractors: 0, passives: 0 }
  const promoters = list.filter((n) => n >= 9).length
  const detractors = list.filter((n) => n <= 6).length
  return { score: Math.round(((promoters - detractors) / list.length) * 100), promoters, detractors, passives: list.length - promoters - detractors }
}

/** 证据强度（后端）：仅文字 1，有截图 1.5，再有技术事件 2；页面结构受损时减半 */
export const strengthLabel = (s) => (s >= 2 ? '强' : s >= 1.5 ? '中' : s >= 1 ? '弱' : '待复核')

/** 报告已按「影响人数 × 严重度 × 证据强度」算好 score，直接沿用 */
export const priorityScore = (f) => f.score ?? 0

export const withheldFor = (pid) => withheld.filter((w) => w.pid === pid)
export const issueCount = (sev) => findings.filter((f) => f.kind === 'issue' && f.sev === sev).length

/** 到 t 为止发生的社区动态（只含说出的内容） */
export function feedUntil(t) {
  return socialEvents.filter((e) => e.t <= t && e.kind !== 'read').slice().reverse()
}

export const span = () => timeline.total
