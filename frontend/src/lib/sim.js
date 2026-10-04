import {
  personas, steps, findings, posts, reactions, reads, withheld, flows, run, RECORDING_SEC_PER_SIM_MIN,
} from '../mock/data.js'

export const DAY = 1440
export const pad = (n) => String(n).padStart(2, '0')

/** 模拟分钟 → "D1 21:10" */
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

export const P = Object.fromEntries(personas.map((p, i) => [p.id, { ...p, index: i }]))
export const F = Object.fromEntries(flows.map((f) => [f.id, f]))
export const findingById = Object.fromEntries(findings.map((f) => [f.id, f]))
export const postById = Object.fromEntries(posts.map((p) => [p.id, p]))

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
export const assignmentLabel = (p) => (p.assignment === 'explore' ? '自由探索' : F[p.assignment].name)

// —— 时间与状态 ——
export const browseStart = (pid) => P[pid].slot
export const browseEnd = (pid) => steps[pid][steps[pid].length - 1].t + 1

/** 人物在全天中的社区行为（发帖、评论、点赞、看帖） */
export const socialEvents = (() => {
  const out = []
  for (const p of posts) {
    out.push({ kind: 'post', pid: p.author, t: p.t, ref: p.id })
    for (const c of p.comments) out.push({ kind: 'comment', pid: c.author, t: c.t, ref: c.id, post: p.id })
  }
  for (const r of reactions) out.push({ kind: 'react', pid: r.pid, t: r.t, ref: r.target })
  for (const r of reads) out.push({ kind: 'read', pid: r.pid, t: r.t, ref: r.post })
  return out.sort((a, b) => a.t - b.t)
})()

export function statusAt(pid, t) {
  const start = browseStart(pid)
  const end = browseEnd(pid)
  if (t >= start && t < end) return 'browse'
  if (socialEvents.some((e) => e.pid === pid && e.kind !== 'read' && t >= e.t && t < e.t + 6)) return 'social'
  if (socialEvents.some((e) => e.pid === pid && e.kind === 'read' && t >= e.t && t < e.t + 3)) return 'social'
  if (t < start) return 'wait'
  return P[pid].outcome === 'quit' ? 'quit' : 'done'
}

/** 当前正在执行的步骤索引（0 基），未开始返回 -1 */
export function stepIndexAt(pid, t) {
  const list = steps[pid]
  let idx = -1
  for (let i = 0; i < list.length; i++) if (list[i].t <= t) idx = i
  return idx
}

export const videoSec = (pid, stepNo) => (steps[pid][stepNo - 1].t - P[pid].slot) * RECORDING_SEC_PER_SIM_MIN + 30

// —— 证据 ——
const kindLabel = { step: '步骤', video: '录像', shots: '截图', console: 'Console', network: 'Network' }
export function evLabel(ev) {
  if (ev.kind === 'step') return `步骤 #${ev.step}`
  if (ev.kind === 'video') return `录像 ${mmss(videoSec(ev.pid, ev.step))}`
  if (ev.kind === 'shots') return `截图 ×${ev.count || 1}`
  if (ev.kind === 'console') return `Console · #${ev.step}`
  if (ev.kind === 'network') return `Network · #${ev.step}`
  return kindLabel[ev.kind]
}
export function resolveEvidence(ev) {
  const p = P[ev.pid]
  const st = steps[ev.pid][ev.step - 1]
  const trace = (st.trace || []).map((line) => {
    const [type, ...rest] = line.split(':')
    const body = rest.join(':')
    if (type === 'console') {
      const [level, ...msg] = body.split(' ')
      return { type, level, text: msg.join(' ') }
    }
    return { type, level: / (4|5)\d\d /.test(body) ? 'error' : 'info', text: body }
  })
  return { persona: p, step: st, stepNo: ev.step, total: steps[ev.pid].length, trace, video: videoSec(ev.pid, ev.step) }
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
export const tasked = personas.filter((p) => p.assignment !== 'explore')
export const taskedDone = tasked.filter((p) => p.outcome === 'success')

export function npsOf(list) {
  const promoters = list.filter((n) => n >= 9).length
  const detractors = list.filter((n) => n <= 6).length
  return { score: Math.round(((promoters - detractors) / list.length) * 100), promoters, detractors, passives: list.length - promoters - detractors }
}

export function priorityScore(f) {
  const sevW = { 1: 4, 2: 3, 3: 2, 4: 1 }[f.sev] || 0
  return (f.affected.length / f.denominator) * f.affected.length * sevW * (f.strength || 0.5)
}

export const withheldFor = (pid) => withheld.filter((w) => w.pid === pid)
export const issueCount = (sev) => findings.filter((f) => f.kind === 'issue' && f.sev === sev).length

// —— 费用：按事件累计，最后归一到实际花费 ——
const costEvents = (() => {
  const ev = []
  for (const pid of Object.keys(steps)) for (const st of steps[pid]) ev.push({ t: st.t, w: P[pid].tech === 'developer' ? 1.3 : 1 })
  for (const e of socialEvents) ev.push({ t: e.t, w: e.kind === 'read' ? 0.15 : 0.45 })
  for (let h = 0; h < 24; h++) ev.push({ t: h * 60, w: 0.6 }) // 每个时间片的 OASIS 推进
  ev.sort((a, b) => a.t - b.t)
  const total = ev.reduce((s, e) => s + e.w, 0)
  let acc = 0
  return ev.map((e) => ({ t: e.t, c: (acc += e.w) / total }))
})()
export function costAt(t) {
  let frac = 0
  for (const e of costEvents) { if (e.t <= t) frac = e.c; else break }
  return run.actual.cny * frac
}
export function callsAt(t) { return Math.round((costAt(t) / run.actual.cny) * run.actual.calls) }

/** 到 t 为止发生的社区动态（只含说出的内容） */
export function feedUntil(t) {
  return socialEvents.filter((e) => e.t <= t && e.kind !== 'read').slice().reverse()
}

export function votesOf(target, t = DAY) {
  return reactions.filter((r) => r.target === target && r.t <= t && r.kind === 'up').length -
    reactions.filter((r) => r.target === target && r.t <= t && r.kind === 'down').length
}
