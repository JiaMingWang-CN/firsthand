// 阶段 C：人物、社区与公开声音先显示摘要，完整内容按需展开。
import { test, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import sample from './fixtures/sample.json'
import { adapt } from '../src/api/adapt.js'
import * as data from '../src/lib/data.js'
import { rebuild, browseStart, withheldFor, statusAt, label } from '../src/lib/sim.js'
import { clock, drawers, closeAllDrawers } from '../src/lib/store.js'
import PersonasView from '../src/views/PersonasView.vue'
import CommunityView from '../src/views/CommunityView.vue'
import ReportView from '../src/views/ReportView.vue'
import VoiceCard from '../src/components/VoiceCard.vue'

// happy-dom 不排版：用两行 / 四行的高度模拟真实截断，展开时恢复完整高度。
function mockOverflow(overflows) {
  vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockImplementation(function () {
    return overflows(this) ? 80 : 40
  })
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockImplementation(function () {
    return overflows(this) && !this.classList.contains('clamped') ? 80 : 40
  })
}

const mounted = []
function render(component, options = {}) {
  const w = mount(component, { attachTo: document.body, global: { stubs: { PageIntro: true } }, ...options })
  mounted.push(w)
  return w
}

beforeEach(() => {
  const copy = structuredClone(sample)
  // 真实样本保留了三个人，收窄报告与看帖关联，避免无关人物干扰页面。
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
  for (const [key, value] of Object.entries(adapt(copy))) data.replaceAll(key === 'span' ? data.timeline : data[key], value)
  rebuild()
  clock.t = data.timeline.total
  closeAllDrawers()
  vi.spyOn(Element.prototype, 'scrollIntoView').mockImplementation(() => {})
})

afterEach(() => {
  while (mounted.length) mounted.pop().unmount()
  closeAllDrawers()
  vi.restoreAllMocks()
})

test('人物默认列表仅保留人物、单行身份、结果、NPS 与有记录的未说出数量，行支持鼠标和键盘打开抽屉', async () => {
  const w = render(PersonasView)
  expect(w.get('[aria-label="列表"]').attributes('aria-pressed')).toBe('true')
  expect(w.find('.cards').exists()).toBe(false)
  expect(w.findAll('thead th').map((c) => c.text())).toEqual(['人物', '身份', '结果', 'NPS', '未说出'])
  const rows = w.findAll('tbody tr')
  expect(rows).toHaveLength(data.personas.length)
  for (const [i, p] of data.personas.entries()) {
    const row = rows[i]
    const cells = row.findAll('td')
    expect(cells).toHaveLength(5)
    expect(cells[0].find('.avatar').exists()).toBe(true)
    expect(cells[0].text()).toContain(p.realname)
    expect(cells[1].text()).toBe(p.age + ' · ' + p.city + ' · ' + p.profession)
    expect(cells[2].text()).toBe(label.status[statusAt(p.id, clock.t)])
    expect(cells[3].text()).toBe(String(data.surveys[p.id].nps))
    expect(cells[4].text()).toBe(withheldFor(p.id).length ? '未说出 ' + withheldFor(p.id).length : '')
    for (const text of [p.bio, '体验时刻', '步数']) expect(row.text()).not.toContain(text)
    for (const selector of ['.attrs', '.spark', '.bg', '.simtime']) expect(row.find(selector).exists()).toBe(false)
  }
  await rows[0].trigger('click')
  expect(drawers.stack[0]).toMatchObject({ type: 'persona', pid: data.personas[0].id })
  closeAllDrawers()
  await rows[1].trigger('keydown', { key: 'Enter' })
  expect(drawers.stack[0]).toMatchObject({ type: 'persona', pid: data.personas[1].id })
  await w.get('[aria-label="卡片"]').trigger('click')
  expect(w.findAll('.cards .pc')).toHaveLength(data.personas.length)
  expect(w.get('.cards .bg').text()).toBe(data.personas[0].bio)
})

test('覆盖要求全部满足时一行展示，详情可展开和收起；未满足时点名并警示', async () => {
  for (const p of data.personas) Object.assign(p, { device: 'mobile', tech: 'developer', patience: 'low', withhold: '高' })
  const w = render(PersonasView)
  const summary = w.get('.coverage-summary')
  expect(summary.text()).toContain('覆盖要求 4/4 已满足')
  for (const [kind, text] of [['poster', '发帖'], ['commenter', '评论'], ['reactor', '点赞'], ['lurker', '潜水']]) {
    expect(summary.text()).toContain(text + ' ' + data.personas.filter((p) => p.participation === kind).length)
  }
  expect(summary.find('.warning').exists()).toBe(false)
  expect(w.find('.dist').exists()).toBe(false)
  await summary.get('button').trigger('click')
  expect(summary.get('button').attributes('aria-expanded')).toBe('true')
  expect(w.findAll('.dist .kpi')).toHaveLength(5)
  await summary.get('button').trigger('click')
  expect(w.find('.dist').exists()).toBe(false)
  for (const p of data.personas) Object.assign(p, { tech: 'normal', withhold: '低' })
  await nextTick()
  expect(summary.get('.warning').text()).toContain('覆盖要求 2/4 已满足 · 未满足：开发者、明显的未说出倾向')
  await summary.get('button').trigger('click')
  expect(w.findAll('.dist .warning')).toHaveLength(2)
})

test('人物搜索和筛选仍有效，未说出为零不显示标签，空结果有提示', async () => {
  data.withheld.splice(0)
  const w = render(PersonasView)
  expect(w.find('tbody .withheld').exists()).toBe(false)
  await w.get('[aria-label="搜索人物"]').setValue(data.personas[0].realname)
  expect(w.findAll('tbody tr')).toHaveLength(1)
  expect(w.get('tbody').text()).toContain(data.personas[0].realname)
  await w.get('[aria-label="搜索人物"]').setValue('')
  await w.findAll('[aria-label="筛选"] button').find((b) => b.text() === '有未说出的').trigger('click')
  expect(w.get('tbody').text()).toContain('没有符合条件的人物')
})

test('社区帖子与评论的证据收成一个按钮，展开后每条仍跳转到原证据；标题打开帖子抽屉', async () => {
  const post = [...data.posts].sort((a, b) => b.t - a.t)[0]
  post.comments.push({ id: 'evidence-comment', author: post.author, t: post.t, body: '带证据的评论', evidence: [...post.evidence] })
  const w = render(CommunityView)
  const card = w.get('.post')
  const group = card.get('.meta .evidence-group')
  expect(group.get('button').text()).toBe('证据 · ' + post.evidence.length)
  expect(group.find('.ev').exists()).toBe(false)
  await group.get('button').trigger('click')
  expect(group.get('button').attributes('aria-expanded')).toBe('true')
  expect(group.findAll('.ev')).toHaveLength(post.evidence.length)
  for (const [i, ev] of post.evidence.entries()) {
    await group.findAll('.ev')[i].trigger('click')
    expect(drawers.stack[0]).toMatchObject({ type: 'evidence', ev })
  }
  await group.get('button').trigger('click')
  expect(group.find('.ev').exists()).toBe(false)
  await card.get('.pt').trigger('click')
  expect(drawers.stack[0]).toMatchObject({ type: 'post', id: post.id })
  expect(card.get('.body').text()).toBe(post.body)
  expect(card.find('.cmts').exists()).toBe(false)
  await card.get('.comments-toggle').trigger('click')
  const comment = card.get('.cmt .evidence-group')
  expect(comment.get('button').text()).toBe('证据 · ' + post.evidence.length)
  expect(comment.find('.ev').exists()).toBe(false)
  await comment.get('button').trigger('click')
  expect(comment.findAll('.ev')).toHaveLength(post.evidence.length)
  await comment.get('.ev').trigger('click')
  expect(drawers.stack[0]).toMatchObject({ type: 'evidence', ev: post.evidence[0] })
})

test('发言权限按当前时刻互斥汇总，体验前只能看帖，名单按需展开', async () => {
  const base = { ...data.personas[0] }
  data.replaceAll(data.personas, ['poster', 'commenter', 'reactor', 'lurker'].map((participation, i) => ({ ...base, id: 'perm' + i, participation, slot: 100 + i * 100 })))
  for (const p of data.personas) data.steps[p.id] = []
  data.posts.splice(0)
  data.reads.splice(0)
  rebuild()
  clock.t = 0
  const w = render(CommunityView, { global: { stubs: { PageIntro: true, SimTimeline: true } } })
  expect(w.get('.permission-summary').text()).toBe('可发帖 0 · 可评论 0 · 只能点赞 0 · 只能看帖 4')
  expect(w.find('.perm').exists()).toBe(false)
  clock.t = browseStart('perm0')
  await nextTick()
  expect(w.get('.permission-summary').text()).toBe('可发帖 1 · 可评论 0 · 只能点赞 0 · 只能看帖 3')
  clock.t = 500
  await nextTick()
  expect(w.get('.permission-summary').text()).toBe('可发帖 1 · 可评论 1 · 只能点赞 1 · 只能看帖 1')
  const toggle = w.get('[aria-controls="permission-list"]')
  await toggle.trigger('click')
  expect(toggle.attributes('aria-expanded')).toBe('true')
  expect(w.findAll('.perm li')).toHaveLength(4)
  expect(w.get('.perm').text()).toContain('可发帖、评论、点赞')
  await toggle.trigger('click')
  expect(w.find('.perm').exists()).toBe(false)
})

test('第 04 节五个子块各默认三条，独立展开到全部并可收起，问卷不再止于六人', async () => {
  mockOverflow((el) => el.matches('.text'))
  const base = { ...data.personas[0] }
  for (let i = 0; i < 4; i++) {
    const id = 'extra' + i
    data.personas.push({ ...base, id, realname: '补充人物' + i, assignment: 'explore' })
    data.steps[id] = [...data.steps[base.id]]
    data.surveys[id] = { ...data.surveys[base.id] }
    data.withheld.push({ ...data.withheld[0], pid: id })
  }
  for (let i = 0; i < 5; i++) data.posts.push({ ...data.posts[0], id: 'extra-post' + i, comments: [] })
  data.replaceAll(data.inconsistencies, data.personas.map((p) => ({ pid: p.id, public: '公开长引文'.repeat(50), private: '私下复核提示'.repeat(50) })))
  rebuild()
  const w = render(ReportView)
  const section = w.get('#voices')
  const blocks = [
    ['.public-block', '.voice', data.posts.length],
    ['.withheld-block', '.voice', data.withheld.length],
    ['.private-block', '.voice', data.personas.length],
    ['#voices', '.trow', data.personas.length, '.silence-toggle'],
    ['#voices', '.inc', data.inconsistencies.length, '.consistency-toggle'],
  ]
  for (const [block, item, total, toggleSelector = '.block-toggle'] of blocks) {
    const area = w.get(block)
    expect(area.findAll(item)).toHaveLength(3)
    const toggle = area.get(toggleSelector)
    expect(toggle.text()).toBe('显示全部 ' + total + ' 条')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    await toggle.trigger('click')
    expect(area.findAll(item)).toHaveLength(total)
    expect(toggle.attributes('aria-expanded')).toBe('true')
    if (item === '.voice') expect(section.findAll('.inc')).toHaveLength(3)
    await toggle.trigger('click')
    expect(area.findAll(item)).toHaveLength(3)
  }
  expect(section.get('.voice .text').classes()).toContain('clamped')
  await section.get('.voice .quote-toggle').trigger('click')
  expect(section.get('.voice .text').classes()).not.toContain('clamped')
  await section.get('.review-toggle').trigger('click')
  expect(section.get('.inc').find('.voice .clamped').exists()).toBe(false)
  await section.get('.trow').trigger('click')
  expect(drawers.stack[0]).toMatchObject({ type: 'persona', tab: 'unsaid' })
})

test('子块不足四条不显示冗余的展开全部按钮；人物抽屉沿用的声音卡默认显示全文', () => {
  data.posts.splice(3)
  data.withheld.splice(3)
  const w = render(ReportView)
  expect(w.find('#voices .block-toggle').exists()).toBe(false)
  const voice = render(VoiceCard, { props: { pid: data.personas[0].id, text: '完整引文'.repeat(100), reason: '完整原因'.repeat(100) } })
  expect(voice.find('.clamped').exists()).toBe(false)
  expect(voice.find('.quote-toggle').exists()).toBe(false)
})

test('紧凑声音卡的引文和原因默认截断，可展开全文再收起', async () => {
  mockOverflow((el) => el.matches('.text, .reason-text'))
  const text = '较长的体验引文'.repeat(80)
  const reason = '较长的隐瞒原因'.repeat(80)
  const w = render(VoiceCard, { props: { compact: true, kind: 'withheld', pid: data.personas[0].id, text, reason } })
  await nextTick()
  const toggle = w.get('.quote-toggle')
  expect(w.findAll('.clamped')).toHaveLength(2)
  expect(w.get('.text').text()).toBe(text)
  expect(w.get('.reason-text').text()).toBe('原因：' + reason)
  await toggle.trigger('click')
  expect(toggle.attributes('aria-expanded')).toBe('true')
  expect(w.find('.clamped').exists()).toBe(false)
  await toggle.trigger('click')
  expect(w.findAll('.clamped')).toHaveLength(2)
})

test('评论逐帖默认折叠，点击评论 N 展开、再点收起；零评论不出现按钮', async () => {
  for (const [i, p] of data.posts.entries()) {
    p.comments = i < 2 ? [{ id: 'comment-' + i, author: p.author, t: p.t, body: '评论内容' + i, evidence: [] }] : []
  }
  const w = render(CommunityView)
  const cards = w.findAll('.post')
  expect(w.find('.cmts').exists()).toBe(false)
  const withComments = cards.filter((card) => card.find('.comments-toggle').exists())
  expect(withComments).toHaveLength(2)
  for (const card of withComments) {
    expect(card.get('.comments-toggle').text()).toBe('评论 1')
    expect(card.get('.comments-toggle').attributes('aria-expanded')).toBe('false')
  }
  const toggle = withComments[0].get('.comments-toggle')
  await toggle.trigger('click')
  expect(toggle.attributes('aria-expanded')).toBe('true')
  expect(withComments[0].get('.cmts').attributes('id')).toBe(toggle.attributes('aria-controls'))
  expect(withComments[0].findAll('.cmt')).toHaveLength(1)
  expect(withComments[1].find('.cmts').exists()).toBe(false)
  await toggle.trigger('click')
  expect(toggle.attributes('aria-expanded')).toBe('false')
  expect(w.find('.cmts').exists()).toBe(false)
})

test('社区正文仅在截断时提供就地展开和收起，缩放后重新测量，不打开抽屉', async () => {
  let clipped = false
  mockOverflow((el) => clipped && el.matches('.body'))
  const w = render(CommunityView)
  await nextTick()
  const card = w.get('.post')
  expect(card.get('.body').classes()).toContain('clamped')
  expect(card.find('.expand-post').exists()).toBe(false)
  clipped = true
  window.dispatchEvent(new Event('resize'))
  await nextTick()
  const toggle = card.get('.expand-post')
  expect(toggle.text()).toBe('展开')
  expect(toggle.attributes('aria-expanded')).toBe('false')
  await toggle.trigger('click')
  expect(toggle.text()).toBe('收起')
  expect(toggle.attributes('aria-expanded')).toBe('true')
  expect(card.get('.body').classes()).not.toContain('clamped')
  expect(drawers.stack).toHaveLength(0)
  window.dispatchEvent(new Event('resize'))
  await nextTick()
  expect(card.get('.expand-post').text()).toBe('收起')
  expect(card.get('.body').classes()).not.toContain('clamped')
  await toggle.trigger('click')
  expect(card.get('.body').classes()).toContain('clamped')
  clipped = false
  window.dispatchEvent(new Event('resize'))
  await nextTick()
  expect(card.find('.expand-post').exists()).toBe(false)
})

test('短引文无展开按钮，原因被截断也能展开；内容更新后重测，卸载移除尺寸监听', async () => {
  mockOverflow((el) => el.matches('.reason-text') && el.textContent.includes('长原因'))
  const remove = vi.spyOn(window, 'removeEventListener')
  const w = render(VoiceCard, { props: { compact: true, pid: data.personas[0].id, text: '短引文', reason: '短原因' } })
  await nextTick()
  expect(w.find('.quote-toggle').exists()).toBe(false)
  await w.setProps({ reason: '长原因'.repeat(40) })
  expect(w.get('.quote-toggle').attributes('aria-expanded')).toBe('false')
  await w.get('.quote-toggle').trigger('click')
  expect(w.get('.quote-toggle').text()).toBe('收起引文')
  expect(w.find('.clamped').exists()).toBe(false)
  window.dispatchEvent(new Event('resize'))
  await nextTick()
  expect(w.get('.quote-toggle').text()).toBe('收起引文')
  expect(w.find('.clamped').exists()).toBe(false)
  await w.get('.quote-toggle').trigger('click')
  expect(w.get('.reason-text').classes()).toContain('clamped')
  await w.setProps({ reason: '短原因' })
  expect(w.find('.quote-toggle').exists()).toBe(false)
  w.unmount()
  mounted.pop()
  expect(remove.mock.calls.some(([event]) => event === 'resize')).toBe(true)
})
