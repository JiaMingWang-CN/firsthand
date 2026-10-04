// 后端数据 → UI 使用的数据形状。纯函数，不依赖 Vue，可用 `node --test` 测试。
//
// 时间轴：模拟分钟 = 距 run_config.start_time 的分钟数（UTC 时刻）。人物的本地时刻单独保存在 localSlot。
// 点赞：后端有意不提供（报告不按点赞排序），所以没有 reactions。
// 技术事件：后端按步骤给出旁路采集的 Console 输出、失败请求与 HTTP 错误摘要（不含请求头），人物本身未必看得到。

const DAY = 1440
const LEVEL = { yes: '会', no: '不会', unsure: '不确定' }
const PAY = { yes: '愿意', no: '不会', unsure: '不确定' }
const OUTCOME = { success: 'success', abandoned: 'quit', failed: 'error' }
const PALETTE = 10

/** 后端严重度 1–5（越大越严重）→ UI 的 S1–S4（S1 致命） */
export const severityOf = (n) => (n >= 5 ? 1 : n === 4 ? 2 : n === 3 ? 3 : 4)

const hasZone = (s) => /(?:[zZ]|[+-]\d{2}:?\d{2})$/.test(s)
/** 带时区的 ISO 时间，或 OASIS 的 "YYYY-MM-DD HH:MM:SS"（UTC，无时区） → 毫秒 */
export const toMs = (value) => Date.parse(hasZone(value) ? value : value.replace(' ', 'T') + 'Z')
/** 本地时间字符串（已带偏移）的当日分钟数 */
export const localMinutes = (iso) => Number(iso.slice(11, 13)) * 60 + Number(iso.slice(14, 16))
/** 时间字符串里的时区偏移（分钟，东为正）；Z 或无偏移为 0 */
export const offsetMinutes = (iso) => {
  const m = /([+-])(\d{2}):?(\d{2})$/.exec(iso || '')
  return m ? (m[1] === '-' ? -1 : 1) * (Number(m[2]) * 60 + Number(m[3])) : 0
}
const mod = (n, m) => ((n % m) + m) % m
/** 人物每个本地整点的刷社区概率 → 运行时钟上的 [{t, v}]，逐日重复 */
export function heatOf(activityByHour, offset, startMs, days) {
  const origin = mod(Math.floor(startMs / 60000), DAY)
  const out = []
  for (const [hour, v] of Object.entries(activityByHour ?? {})) {
    const first = mod(mod(Number(hour) * 60 - offset, DAY) - origin, DAY)
    for (let d = 0; d < days; d++) out.push({ t: first + d * DAY, v })
  }
  return out.sort((a, b) => a.t - b.t)
}

const unique = (items, key) => {
  const seen = new Set()
  return items.filter((item) => { const k = key(item); if (seen.has(k)) return false; seen.add(k); return true })
}

function describeAction(action) {
  const [name, args = {}] = Object.entries(action)[0] || ['', {}]
  switch (name) {
    case 'scroll': return `${args.down === false ? '向上' : '向下'}滚动${args.pages ? ` ${args.pages} 屏` : ''}`
    case 'click': return `点击页面元素${args.index != null ? ` #${args.index}` : ''}`
    case 'input': return `输入文字${args.text ? `：${String(args.text).slice(0, 24)}` : ''}`
    case 'navigate': case 'go_to_url': return `打开 ${args.url ?? '页面'}`
    case 'wait': return '等待页面'
    case 'done': return '结束体验'
    default: return name || '未知动作'
  }
}
const pathOf = (url) => {
  try { const u = new URL(url); return u.pathname + u.search } catch (e) { return url || '' }
}

/** 体验标题：公开文本的第一行是固定开头时取第二行 */
export function titleOf(content) {
  const lines = String(content || '').split('\n').map((l) => l.trim()).filter(Boolean)
  const line = lines.length > 1 && /[：:]$/.test(lines[0]) ? lines[1] : lines[0] || ''
  return line.length > 44 ? `${line.slice(0, 44)}…` : line
}

function adaptSteps(exp, slot) {
  const snaps = Object.fromEntries(exp.snapshots.map((s) => [s.evidence_id, s]))
  const emotions = Object.fromEntries((exp.assessment?.emotions ?? []).map((e) => [e.step, e]))
  let seconds = 0
  return exp.steps.map((s) => {
    const before = snaps[s.before], after = snaps[s.after], e = emotions[s.step]
    const t = slot + seconds / 60
    seconds += s.seconds
    return {
      n: s.step, ref: s.ref_id, t,
      act: s.actions.map(describeAction).join('；') || '观察页面',
      url: after?.url ?? before?.url ?? '', path: pathOf(after?.url ?? before?.url),
      sat: e ? (e.satisfaction - 3) / 2 : 0, conf: e ? (e.confusion - 1) / 4 : 0,
      think: e?.reason ?? '', observation: s.agent_observation,
      stalled: s.stalled, degraded: s.page_structure_degraded,
      shots: { before: before?.screenshot_url ?? null, after: after?.screenshot_url ?? null },
      snaps: { before: s.before, after: s.after },
      videoAt: { [s.before]: before?.video_seconds ?? null, [s.after]: after?.video_seconds ?? null },
      video: before?.video_seconds ?? null, trace: s.trace ?? [],
    }
  })
}

/** 证据条目：每个引用最多生成 步骤 / 录像 / 截图 三种入口，指向其首个步骤；snapshot 是所引的截图，录像据此定位 */
function evidenceOf(pid, stepNumbers, shotCount, snapshot, hasVideo = true) {
  const step = stepNumbers[0]
  if (step == null) return []
  const out = [{ pid, step, kind: 'step', snapshot }]
  if (hasVideo) out.push({ pid, step, kind: 'video', snapshot })
  if (shotCount) out.push({ pid, step, kind: 'shots', count: shotCount, snapshot })
  return out
}
/** 该步骤里被引用的那张截图，优先操作前 */
const citedSnapshot = (step, ids) => (step ? [step.before, step.after].find((id) => ids.has(id)) : undefined)

/** 每个人物的体验结论：ref → {title, kind, steps, evidence} */
function findingIndex(experiences) {
  const index = {}
  for (const [pid, exp] of Object.entries(experiences)) {
    for (const f of exp.assessment?.findings ?? []) {
      const ids = new Set(f.evidence_ids)
      const cited = exp.steps.filter((s) => ids.has(s.before) || ids.has(s.after))
      const steps = cited.map((s) => s.step)
      index[f.ref_id] = { pid, title: f.title, kind: f.kind, steps, evidence: evidenceOf(pid, steps, ids.size, citedSnapshot(cited[0], ids)) }
    }
  }
  return index
}

const stepRange = (steps) => (steps.length ? (steps.length === 1 ? `#${steps[0]}` : `#${steps[0]}–${steps[steps.length - 1]}`) : '')

export function adapt({ overview, personas: rows, experiences, community, report }) {
  const product = overview.product ?? { metadata: {}, summary: {}, flows: [] }
  const config = overview.run_config ?? {}
  const sliceMinutes = config.time_slice_minutes ?? 60
  const scheduled = rows.map((r) => r.scheduled_at).filter(Boolean).map(toMs)
  const startMs = config.start_time ? Date.parse(config.start_time)
    : scheduled.length ? Math.floor(Math.min(...scheduled) / 86400000) * 86400000 : Date.now()
  const sim = (value) => (toMs(value) - startMs) / 60000

  const flows = (product.flows ?? []).map((f, i) => ({ id: `F${i + 1}`, name: f.name, short: f.name.length > 6 ? f.name.slice(0, 6) : f.name }))
  const flowId = (name) => flows.find((f) => f.name === name)?.id ?? 'explore'

  // —— 人物与步骤 ——
  const personas = [], steps = {}
  rows.forEach((row, i) => {
    const p = row.persona, bp = p.browsing_profile, sched = p.schedule, exp = experiences[row.persona_id]
    const slot = row.scheduled_at ? sim(row.scheduled_at) : row.browse_slice * sliceMinutes
    const tzOffset = offsetMinutes(row.scheduled_at)
    personas.push({
      id: row.persona_id, color: `var(--p${(i % PALETTE) + 1})`,
      realname: p.realname, username: p.username, gender: p.gender, age: p.age, city: p.city, timezone: p.timezone,
      profession: p.profession, industry: p.industry, education: p.education, income: p.income_level,
      life: p.life_context, history: p.product_history, bio: p.bio, narrative: p.persona, topics: p.interested_topics,
      mbti: p.mbti, style: p.communication_style,
      bigFive: { O: p.big_five.openness, C: p.big_five.conscientiousness, E: p.big_five.extraversion, A: p.big_five.agreeableness, N: p.big_five.neuroticism },
      device: bp.device, tech: bp.tech_level, patience: bp.patience, maxSteps: bp.max_steps, stall: bp.stall_limit,
      motivation: bp.motivation, motivationDetail: bp.motivation_detail, account: bp.account_role, tools: bp.tools,
      assignment: bp.assignment.type === 'task' ? flowId(bp.assignment.flow) : 'explore',
      wake: sched.wake, sleep: sched.sleep, slot, localSlot: row.scheduled_at ? localMinutes(row.scheduled_at) : null,
      tzOffset, state: exp?.state_at_browse ?? sched.state_at_browse, activity: sched.activity_by_hour,
      heat: heatOf(sched.activity_by_hour, tzOffset, startMs, config.duration_days ?? 1),
      participation: p.participation, candor: p.disclosure.candor, withhold: p.disclosure.withhold_tendency,
      withholdReasons: p.disclosure.withhold_reasons,
      outcome: exp ? OUTCOME[exp.outcome] ?? 'error' : 'error',
      outcomeReason: exp?.reason ?? '没有通过校验的体验记录',
      outcomeSource: row.experience?.outcome_source ?? null, hasExperience: Boolean(exp), jobState: row.job_state,
      survey: row.survey, replay: exp ? { url: exp.replay.viewer_url, basis: exp.replay.offset_basis } : null,
    })
    steps[row.persona_id] = exp ? adaptSteps(exp, slot) : []
  })
  const outcomeOf = Object.fromEntries(personas.map((p) => [p.id, p.outcome]))
  const withExperience = personas.filter((p) => p.hasExperience).length
  const ref = findingIndex(experiences)

  // —— 报告：问题与亮点 ——
  const findings = []
  const sections = report?.report?.sections ?? { issues: [], highlights: [] }
  const toFinding = (kind, item, n) => {
    const evidence = item.evidence.flatMap((e) => {
      const first = experiences[e.persona_id]?.steps.find((s) => s.step === e.steps[0])
      const ids = new Set(e.video.map((v) => v.evidence_id))
      return evidenceOf(e.persona_id, e.steps, e.screenshots.length, citedSnapshot(first, ids), e.video.length > 0)
    })
    return {
      id: `${kind === 'issue' ? 'I' : 'H'}-${String(n + 1).padStart(2, '0')}`, kind, sev: kind === 'issue' ? severityOf(item.severity) : 3,
      severity: item.severity, flow: null, title: item.title, summary: item.detail, cause: '',
      affected: item.affected_personas, denominator: withExperience,
      quit: item.affected_personas.filter((pid) => outcomeOf[pid] !== 'success'),
      evidence: unique(evidence, (e) => `${e.pid}#${e.step}#${e.kind}`),
      quotes: item.evidence.map((e) => ({ ref: e.ref_id, pid: e.persona_id, quote: e.quote })),
      impact: item.affected_personas.length, strength: item.evidence_strength, score: item.score, reviewFlags: item.review_flags,
    }
  }
  sections.issues.forEach((item, n) => findings.push(toFinding('issue', item, n)))
  sections.highlights.forEach((item, n) => findings.push(toFinding('highlight', item, n)))

  // —— 社区 ——
  const publicBodies = new Map(community.withheld.filter((d) => d.public_body).map((d) => [`${d.persona_id}|${d.public_body}`, d.shared]))
  const evidenceForPost = (post) => (publicBodies.get(`${post.persona_id}|${post.content}`) ?? []).flatMap((r) => ref[r]?.evidence.slice(0, 2) ?? [])
  const posts = community.posts.map((p) => ({
    id: `post-${p.post_id}`, author: p.persona_id, t: sim(p.created_at), title: titleOf(p.content), body: p.content,
    evidence: unique(evidenceForPost(p), (e) => `${e.pid}#${e.step}#${e.kind}`).slice(0, 3),
    comments: p.comments.map((c) => ({ id: `c-${c.comment_id}`, author: c.persona_id, t: sim(c.created_at), body: c.content, evidence: [] })),
  }))

  const expectations = {}
  for (const [pid, exp] of Object.entries(experiences)) {
    for (const line of exp.expectations ?? []) {
      const m = /^体验前我看到帖子 #(\d+) 说：/.exec(line)
      if (m) expectations[`${pid}|${m[1]}`] = line.replace(/^体验前我看到帖子 #\d+ 说：/, '')
    }
  }
  const reads = community.reads.map((r) => ({
    pid: r.persona_id, t: r.slice_index * sliceMinutes, post: `post-${r.post_id}`, before: r.before_experience,
    expectation: r.before_experience ? expectations[`${r.persona_id}|${r.post_id}`] : undefined,
  }))

  // 沉默信号：有报告时以报告为准（它也把潜水者的全部体验算作沉默）；没有报告时由表达过滤记录推出
  const participation = Object.fromEntries(personas.map((p) => [p.id, p.participation]))
  const sliceOf = Object.fromEntries(community.withheld.map((d) => [d.ref_id, d.slice_index]))
  const signals = report?.report?.silence_signals ?? null
  const rawSignals = signals ?? community.withheld.flatMap((d) => d.withheld.map((item) => ({
    persona_id: d.persona_id, source: participation[d.persona_id] === 'lurker' ? 'lurker' : 'withheld', finding_id: item.finding_id,
    reason: item.reason, refs: [d.ref_id], also_public: alsoPublicFallback(d.persona_id, item.finding_id), review_flags: [] })))
  function alsoPublicFallback(pid, findingId) {
    return community.withheld.some((d) => d.persona_id === pid && d.public_body && d.shared.includes(findingId))
  }
  const withheld = unique(rawSignals, (s) => `${s.persona_id}|${s.finding_id}`).map((s) => {
    const f = ref[s.finding_id]
    const lurker = s.source === 'lurker'
    const slice = sliceOf[(s.refs ?? []).find((r) => r.startsWith('disclosure:'))]
    return {
      pid: s.persona_id, t: lurker || slice == null ? null : slice * sliceMinutes, item: f?.title ?? s.title ?? s.finding_id,
      kind: f?.kind ?? s.kind ?? null, reason: s.reason, evidence: f?.evidence ?? [], range: stepRange(f?.steps ?? []),
      lurker, alsoPublic: Boolean(s.also_public), reviewFlags: s.review_flags ?? [],
    }
  })

  // —— 私下问卷 ——
  const titleOfRef = (r) => (r ? ref[r]?.title ?? r : '—')
  const surveys = {}
  for (const s of community.surveys) {
    surveys[s.persona_id] = {
      nps: s.nps, keep: LEVEL[s.continue_using], pay: PAY[s.would_pay], worst: titleOfRef(s.biggest_issue), best: titleOfRef(s.favorite),
      unspoken: s.unsaid.length ? s.unsaid.map((u) => titleOfRef(u.finding_id)).join('；') : '没有。',
      unspokenWhy: s.unsaid[0]?.reason, changed: s.opinion_changed ? s.explanation : '没有。',
      changedBy: s.influencing_post_ids.length ? `post-${s.influencing_post_ids[0]}` : null,
      changedByAll: s.influencing_post_ids.map((id) => `post-${id}`), explanation: s.explanation,
      hasExperience: s.has_experience, flags: s.flags,
    }
  }

  const inconsistencies = (report?.report?.consistency ?? []).filter((c) => c.flags.length).map((c) => ({
    pid: c.persona_id, public: `公开发言 ${c.public_items} 条`, private: c.flag_notes.join('；'), flags: c.flags, evidence: [],
  }))

  // —— 运行信息 ——
  const maxT = Math.max(0, ...Object.values(steps).flat().map((s) => s.t + 1), ...posts.flatMap((p) => [p.t, ...p.comments.map((c) => c.t)]))
  const span = Math.max((config.duration_days ?? 1) * DAY, Math.ceil(maxT / 60) * 60)
  const meta = product.metadata ?? {}
  const summary = product.summary ?? {}
  const configuration = overview.configuration
  return {
    span: { total: span, sliceMinutes, startMs },
    product: {
      name: meta.name ?? '产品', url: meta.url, positioning: summary.positioning, targetUsers: summary.target_users,
      allowedDomains: meta.allowed_domains ?? [], forbidden: meta.forbidden_actions ?? [],
      accounts: (meta.test_accounts ?? []).map((a) => ({ role: a.role, desc: a.description })), features: summary.features ?? [],
    },
    flows, personas, steps, findings, posts, reads, withheld, surveys, inconsistencies,
    scout: report?.report?.scout?.discrepancies ?? [],
    run: {
      id: overview.id, title: `${meta.name ?? '产品'} · 模拟体验`, passed: overview.passed, status: overview.status,
      startedAt: overview.started_at, endedAt: overview.finished_at, simDays: config.duration_days ?? 1, sliceMinutes,
      concurrency: configuration.max_browser_concurrency, model: [configuration.provider, configuration.model].filter(Boolean).join(' / '),
      limitations: overview.limitations ?? [], usage: overview.usage, audit: overview.audit, coverage: overview.coverage,
      report: report ? { id: report.id, result: report.result, overview: report.report.overview, silence: report.report.silence_signals,
        dynamics: report.report.opinion_dynamics, timeSlots: report.report.time_slots, scout: report.report.scout,
        rejected: report.report.rejected_claims } : null,
    },
  }
}
