// 运行：node --test frontend/test
// fixtures/sample.json 取自真实样本 phase4-20261003T071619710132Z（3 名人物：发帖者 p01、评论者 p03、潜水者 p05）及其阶段 5 报告，已去掉回放链接。
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { adapt, severityOf, toMs, localMinutes, offsetMinutes, heatOf, titleOf } from '../src/api/adapt.js'

const sample = JSON.parse(readFileSync(new URL('./fixtures/sample.json', import.meta.url), 'utf8'))
const model = adapt(structuredClone(sample))
const byId = Object.fromEntries(model.personas.map((p) => [p.id, p]))

test('后端严重度 1–5 翻转为 S1–S4（S1 致命）', () => {
  assert.deepEqual([5, 4, 3, 2, 1].map(severityOf), [1, 2, 3, 4, 4])
})

test('时间解析：OASIS 无时区字符串按 UTC，带偏移的按偏移；本地分钟取字符串本身', () => {
  assert.equal(toMs('2026-10-03 01:00:00'), Date.parse('2026-10-03T01:00:00Z'))
  assert.equal(toMs('2026-10-03T09:40:00+08:00'), Date.parse('2026-10-03T01:40:00Z'))
  assert.equal(localMinutes('2026-10-03T13:20:00+08:00'), 800)
})

test('人物的体验时刻相对运行起点，本地时刻另存', () => {
  const start = Date.parse(sample.overview.run_config.start_time)
  assert.equal(byId.p03.slot, (Date.parse('2026-10-03T13:20:00+08:00') - start) / 60000)
  assert.equal(byId.p03.localSlot, 800)
  assert.equal(model.span.total >= 1440, true)
})

test('步骤沿体验时刻推进，满意与困惑被归一到 UI 的区间并带真实截图地址', () => {
  const steps = model.steps.p03
  assert.equal(steps.length, byId.p03 && sample.experiences.p03.steps.length)
  assert.equal(steps[0].t, byId.p03.slot)
  assert.ok(steps.every((s, i) => i === 0 || s.t > steps[i - 1].t))
  assert.ok(steps.every((s) => s.sat >= -1 && s.sat <= 1 && s.conf >= 0 && s.conf <= 1))
  assert.match(steps[0].shots.before, /^\/api\/runs\/.+\/files\/p03\/screenshots\/.+\.png$/)
  assert.equal(typeof steps[0].video, 'number')
  assert.equal(steps[0].ref, 'p03:step:1')
})

test('动作被描述成人能读的中文', () => {
  const acts = Object.values(model.steps).flat().map((s) => s.act)
  assert.ok(acts.some((a) => /滚动/.test(a)))
  assert.ok(acts.every((a) => !a.startsWith('{')))
})

test('问题与亮点来自报告：严重度翻转、证据可定位、被引用人数按有体验的人数计', () => {
  const issues = model.findings.filter((f) => f.kind === 'issue')
  assert.equal(issues.length, sample.report.report.sections.issues.length)
  assert.equal(issues[0].id, 'I-01')
  assert.equal(issues[0].sev, severityOf(sample.report.report.sections.issues[0].severity))
  assert.equal(issues[0].denominator, 3)
  assert.ok(issues[0].evidence.every((e) => e.pid && e.step >= 1 && ['step', 'video', 'shots'].includes(e.kind)))
  assert.ok(model.findings.filter((f) => f.kind === 'highlight').every((f) => f.id.startsWith('H-')))
})

test('没有报告时没有问题清单，其余数据照常', () => {
  const bare = adapt({ ...structuredClone(sample), report: null })
  assert.deepEqual(bare.findings, [])
  assert.equal(bare.run.report, null)
  assert.equal(bare.personas.length, 3)
})

test('帖子时间换算为模拟分钟，标题去掉固定开头', () => {
  const post = model.posts[0]
  assert.equal(post.t, (toMs(sample.community.posts[0].created_at) - model.span.startMs) / 60000)
  assert.ok(post.title.length > 0 && !post.title.endsWith('：'))
  assert.equal(titleOf('我这次用下来：\n首屏很清楚。'), '首屏很清楚。')
  assert.equal(titleOf('没有固定开头'), '没有固定开头')
})

test('未说出的内容按（人物, 结论）去重；潜水者没有发言时刻', () => {
  const keys = model.withheld.map((w) => `${w.pid}|${w.item}`)
  assert.equal(new Set(keys).size, keys.length)
  const lurker = model.withheld.filter((w) => w.lurker)
  assert.ok(lurker.length > 0 && lurker.every((w) => w.t === null && byId[w.pid].participation === 'lurker'))
  assert.ok(model.withheld.every((w) => w.reason))
})

test('读帖区分体验前后，体验前的读帖带预期', () => {
  assert.ok(model.reads.every((r) => r.post.startsWith('post-') && typeof r.before === 'boolean'))
  assert.ok(model.reads.filter((r) => !r.before).every((r) => r.expectation === undefined))
})

test('问卷：枚举译成中文，影响观点的帖子编号带 post- 前缀；没有点赞数据', () => {
  const s = model.surveys.p01
  assert.ok(['会', '不会', '不确定'].includes(s.keep))
  assert.ok(Number.isInteger(s.nps))
  assert.deepEqual(model.surveys.p03.changedByAll.every((id) => id.startsWith('post-')), true)
  assert.equal('reactions' in model, false)
})

test('用量只有模型和 token，没有价格', () => {
  assert.ok(model.run.usage.models.length >= 1)
  const keys = (value) => (value && typeof value === 'object'
    ? Object.entries(value).flatMap(([k, v]) => [k, ...keys(v)]) : [])
  assert.deepEqual(keys(model.run).filter((k) => /usd|price|cny|cost/i.test(k)), [])
})

test('时区偏移与刷社区热度：本地整点换算到 UTC 运行时钟', () => {
  assert.deepEqual([offsetMinutes('2026-10-03T09:40:00+08:00'), offsetMinutes('2026-10-03T09:40:00-05:30'), offsetMinutes('2026-10-03T01:40:00Z')], [480, -330, 0])
  const start = Date.parse('2026-10-03T00:00:00Z')
  // 东八区本地 09:00 = UTC 01:00 = 运行时钟第 60 分钟；两天的运行逐日重复
  assert.deepEqual(heatOf({ 9: 0.7 }, 480, start, 2), [{ t: 60, v: 0.7 }, { t: 1500, v: 0.7 }])
  // 本地 02:00 = 前一天 UTC 18:00 = 运行时钟第 1080 分钟
  assert.deepEqual(heatOf({ 2: 0.3 }, 480, start, 1), [{ t: 1080, v: 0.3 }])
  // 运行起点不在 UTC 零点时，相对起点计
  assert.deepEqual(heatOf({ 9: 0.7 }, 480, Date.parse('2026-10-03T06:00:00Z'), 1), [{ t: 1140, v: 0.7 }])
})

test('每个人物的热度与其时区一致', () => {
  for (const p of model.personas) {
    assert.equal(p.tzOffset, offsetMinutes(sample.personas.find((r) => r.persona_id === p.id).scheduled_at))
    assert.ok(p.heat.every((h) => h.t >= 0 && h.t < model.span.total))
  }
})

test('沉默信号以报告为准，没有报告时由表达过滤记录推出', () => {
  const seen = new Set()
  const signals = sample.report.report.silence_signals.filter((x) => { const k = `${x.persona_id}|${x.finding_id}`; return seen.has(k) ? false : seen.add(k) })
  assert.equal(model.withheld.length, signals.length)
  assert.equal(model.withheld.filter((w) => w.lurker).length, signals.filter((x) => x.source === 'lurker').length)
  assert.equal(model.withheld.filter((w) => w.alsoPublic).length, signals.filter((x) => x.also_public).length)
  const bare = adapt({ ...structuredClone(sample), report: null })
  assert.ok(bare.withheld.length > 0 && bare.withheld.every((w) => w.reason && w.pid))
})

test('“未完成”只统计结果已知且不是成功的人；报告里出现本次运行没有的人物不算', () => {
  const input = structuredClone(sample)
  input.experiences.p03.outcome = 'abandoned'
  input.report.report.sections.issues[0].affected_personas = ['p01', 'p03', 'p99']
  const issue = adapt(input).findings.find((f) => f.id === 'I-01')
  assert.deepEqual(issue.unfinished, ['p03'])
  assert.equal('quit' in issue, false)
})
