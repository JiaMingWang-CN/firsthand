// 阶段 B：列表先给结论，细节和方法说明按需展开。
import { test, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import sample from './fixtures/sample.json'
import { adapt } from '../src/api/adapt.js'
import * as data from '../src/lib/data.js'
import { rebuild } from '../src/lib/sim.js'
import { drawers, closeAllDrawers } from '../src/lib/store.js'
import FindingCard from '../src/components/FindingCard.vue'
import EvidenceView from '../src/components/EvidenceView.vue'
import ReportView from '../src/views/ReportView.vue'

const mounted = []
function render(component, options = {}) {
  const w = mount(component, { attachTo: document.body, global: { stubs: { PageIntro: true } }, ...options })
  mounted.push(w)
  return w
}

beforeEach(() => {
  const copy = structuredClone(sample)
  // 样本只保留了三个人，报告中的关联也收窄到相同人物。
  const kept = new Set(copy.personas.map((p) => p.persona_id))
  const report = copy.report.report
  for (const key of ['issues', 'highlights']) {
    report.sections[key] = report.sections[key].map((f) => ({ ...f,
      affected_personas: f.affected_personas.filter((pid) => kept.has(pid)),
      evidence: f.evidence.filter((e) => kept.has(e.persona_id)),
    })).filter((f) => f.evidence.length)
  }
  report.silence_signals = report.silence_signals.filter((s) => kept.has(s.persona_id))
  report.consistency = report.consistency.filter((c) => kept.has(c.persona_id))
  const posts = new Set(copy.community.posts.map((p) => p.post_id))
  copy.community.reads = copy.community.reads.filter((r) => posts.has(r.post_id))
  copy.overview.limitations = ['合成人物样本较小，仅供方向参考。']
  const adapted = adapt(copy)
  for (const [key, value] of Object.entries(adapted)) data.replaceAll(key === 'span' ? data.timeline : data[key], value)
  rebuild()
  closeAllDrawers()
  vi.spyOn(Element.prototype, 'scrollIntoView').mockImplementation(() => {})
})

afterEach(() => {
  while (mounted.length) mounted.pop().unmount()
  closeAllDrawers()
  vi.restoreAllMocks()
})

test.each(['issue', 'highlight'])('%s 在列表默认折叠，可展开和收起完整内容，标题仍打开抽屉', async (kind) => {
  const f = data.findings.find((f) => f.kind === kind)
  const w = render(FindingCard, { props: { f } })
  const toggle = w.get('.toggle')
  expect(toggle.attributes('aria-expanded')).toBe('false')
  expect(w.get('.impact').text()).toBe('影响 ' + f.affected.length + '/' + f.denominator + ' 人')
  for (const selector of ['.why', '.facts', '.evs', '.unfinished']) expect(w.find(selector).exists()).toBe(false)
  await toggle.trigger('click')
  expect(toggle.attributes('aria-expanded')).toBe('true')
  expect(w.get('.why').text()).toBe(f.summary)
  expect(w.find('.people').exists()).toBe(true)
  expect(w.find('.evs').exists()).toBe(true)
  await toggle.trigger('click')
  expect(toggle.attributes('aria-expanded')).toBe('false')
  expect(w.find('.why').exists()).toBe(false)
  await w.get('.title').trigger('click')
  expect(drawers.stack[0]).toMatchObject({ type: 'finding', id: f.id })
})

test('有证据的卡片在抽屉默认展开，证据仍能打开第二层抽屉', async () => {
  const f = data.findings.find((f) => f.kind === 'issue')
  const w = render(FindingCard, { props: { f }, global: { provide: { inDrawer: true } } })
  expect(w.get('.why').text()).toBe(f.summary)
  expect(w.find('.facts').exists()).toBe(true)
  expect(w.find('.toggle').exists()).toBe(false)
  drawers.stack.push({ type: 'persona', pid: f.affected[0], history: [] })
  await w.get('.seg-ev').trigger('click')
  expect(drawers.stack).toHaveLength(2)
  expect(drawers.stack[1].type).toBe('evidence')
})

test.each([false, true])('无证据卡片保留标签并默认折叠（抽屉：%s）', async (inDrawer) => {
  const f = { ...data.findings[0], evidence: [] }
  const w = render(FindingCard, { props: { f }, global: { provide: { inDrawer } } })
  expect(w.get('.tag.noev').text()).toBe('无证据')
  expect(w.get('.toggle').attributes('aria-expanded')).toBe('false')
  expect(w.find('.why').exists()).toBe(false)
  await w.get('.toggle').trigger('click')
  expect(w.get('.why').text()).toBe(f.summary)
  expect(w.find('.evs').exists()).toBe(false)
})

test('总览仅三张 KPI，每张一行辅助说明；沉默摘要移到第 04 节', async () => {
  const w = render(ReportView)
  const cards = w.findAll('#ov .kpi')
  expect(cards).toHaveLength(3)
  expect(cards.map((c) => c.get('.k').text())).toEqual(['体验完成', '推荐意愿 NPS', '问题'])
  for (const c of cards) expect(c.findAll('div.d')).toHaveLength(1)
  expect(w.get('#ov .kpis').classes()).toContain('g3')
  expect(cards[1].get('.d').attributes('title')).toContain('仅作方向参考')
  expect(w.get('#voices .silence-summary').text()).toContain('条体验没有在社区说出 · 发言者')
  expect(w.get('#voices .silence-summary').attributes('title')).toContain('同一体验可能被多次隐瞒')
  expect(w.find('#ov .src-note').exists()).toBe(false)
  expect(w.find('#ov .cov').exists()).toBe(false)
  const distribution = w.get('#ov details')
  expect(distribution.element.open).toBe(false)
  expect(distribution.get('summary').text()).toBe('查看推荐意愿分布')
  await distribution.get('summary').trigger('click')
  expect(distribution.element.open).toBe(true)
  expect(distribution.get('[role="img"]').attributes('aria-label')).toContain('推荐意愿分布')
})

test('关于这份报告默认折叠，集中判定来源、覆盖与局限性，并进入目录', async () => {
  const w = render(ReportView)
  const about = w.get('details#about')
  expect(about.element.open).toBe(false)
  expect(about.text()).toContain('任务成败的判定来源')
  for (const text of [...data.run.report.overview.coverage_notes, ...data.run.limitations]) {
    expect(about.text()).toContain(text)
    expect(w.findAll('.covl li').filter((li) => li.text() === text)).toHaveLength(1)
  }
  expect(about.text()).toContain(data.run.model)
  expect(about.text()).toContain(new Date(data.run.startedAt).toLocaleString('zh-CN', { hour12: false }))
  expect(about.text()).not.toContain(data.run.startedAt)
  expect(w.get('.toc a[href="#about"]').text()).toContain('关于这份报告')
  await about.get('summary').trigger('click')
  expect(about.element.open).toBe(true)
})

test('折叠列表仍响应 J/K 和 Enter，详情开关的 Enter 不会误开抽屉', async () => {
  const w = render(ReportView)
  await w.trigger('keydown', { key: 'j' })
  expect(w.findAll('#issues .finding.active')).toHaveLength(1)
  const first = w.get('#issues .finding.active').attributes('id')
  await w.trigger('keydown', { key: 'j' })
  expect(w.get('#issues .finding.active').attributes('id')).not.toBe(first)
  await w.trigger('keydown', { key: 'k' })
  expect(w.get('#issues .finding.active').attributes('id')).toBe(first)
  await w.get('#issues .toggle').trigger('keydown', { key: 'Enter' })
  expect(drawers.stack).toHaveLength(0)
  await w.get('#issues .toggle').trigger('click')
  expect(w.get('#issues .toggle').attributes('aria-expanded')).toBe('true')
  await w.trigger('keydown', { key: 'Enter' })
  expect(drawers.stack[0]).toMatchObject({ type: 'finding', id: first })
})

test('证据元信息默认只显示情绪，可展开设备、时区和观察权限，再收起', async () => {
  const ev = data.findings[0].evidence[0]
  const p = data.personas.find((p) => p.id === ev.pid)
  const w = render(EvidenceView, { props: { ev }, global: { stubs: { Recording: true } } })
  const toggle = w.get('.meta-toggle')
  expect(toggle.attributes('aria-expanded')).toBe('false')
  expect(w.findAll('.tags .tag')).toHaveLength(1)
  expect(w.find('.extra-meta').exists()).toBe(false)
  expect(w.find('.shot').exists()).toBe(true)
  expect(w.find('.think').exists()).toBe(true)
  expect(w.find('recording-stub').exists()).toBe(true)
  await toggle.trigger('click')
  expect(toggle.attributes('aria-expanded')).toBe('true')
  expect(w.get('.extra-meta').text()).toContain(p.device === 'mobile' ? '390×844' : '1440×900')
  expect(w.get('.extra-meta').text()).toContain(p.timezone)
  expect(w.get('.perm').text()).toContain(p.tools.length ? '该人物可以通过' : '该人物看不到')
  await toggle.trigger('click')
  expect(toggle.attributes('aria-expanded')).toBe('false')
  expect(w.find('.extra-meta').exists()).toBe(false)
})
