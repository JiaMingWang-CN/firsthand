// 阶段 D：现场与审核先给摘要，长列表和开发者细节按需展开。
import { test, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick, reactive } from 'vue'
import { createRouter, createMemoryHistory } from 'vue-router'
import sample from './fixtures/sample.json'
import { adapt } from '../src/api/adapt.js'
import * as data from '../src/lib/data.js'
import { rebuild } from '../src/lib/sim.js'
import { clock, closeAllDrawers, settleConfirm } from '../src/lib/store.js'
import SimTimeline from '../src/components/SimTimeline.vue'
import LiveView from '../src/views/LiveView.vue'
import ReviewView from '../src/views/ReviewView.vue'
import NewRunView from '../src/views/NewRunView.vue'
import JobView from '../src/views/JobView.vue'
import { api } from '../src/api/client.js'

vi.mock('../src/api/client.js', () => ({ api: {
  draft: vi.fn(), jobs: vi.fn(), job: vi.fn(), jobLive: vi.fn(), jobShot: vi.fn(),
  decide: vi.fn(), simulate: vi.fn(), editDraft: vi.fn(), capabilities: vi.fn(), checkManual: vi.fn(), newDraft: vi.fn(),
} }))

const PERSONA = (i) => ({
  persona_id: `p0${i}`, realname: `人物${i}`, age: 30, gender: '女', profession: '设计师', city: '上海', timezone: 'Asia/Shanghai', bio: '简介',
  persona: '叙述', participation: 'poster', browsing_profile: { device: 'mobile', tech_level: 'novice', patience: 'low', motivation: '随便看看',
    assignment: { type: 'explore', flow: null }, tools: [], max_steps: 30 },
  schedule: { wake: '07:00', sleep: '23:00', state_at_browse: '通勤路上', browse_day: i }, disclosure: { candor: '中', withhold_tendency: '高', withhold_reasons: ['怕显得不会用'] },
  sampling: { temperature: 0.6 + i / 10, top_p: 0.9, presence_penalty: 0.1 },
})
const DRAFT = {
  id: 'phase1-new', status: 'pending', valid: true, draft_sha256: 'a'.repeat(64), approval: { status: 'pending' },
  manual: { name: '示例产品', url: 'https://example.com', flows: ['注册'] }, product: { positioning: '定位', target_users: '用户', features: ['功能'] },
  run_config: { start_time: '2026-10-03T00:00:00Z', duration_days: 1, time_slice_minutes: 60, max_concurrency: 5 }, cohort_rationale: '分布说明',
  personas: [PERSONA(1), PERSONA(2)], schedule: [{ persona_id: 'p01', local_time: '2026-10-03T09:40:00+08:00', slice_index: 1 }, { persona_id: 'p02', local_time: '2026-10-03T21:10:00+08:00', slice_index: 13 }],
  distribution: ['- 性别：女 2'], issues: [], capability: { model: 'm' }, simulations: [],
  sampling: { probed: true, chat: true, configured_api: true, thinking: 'disabled' }, limits: { personas: [2, 99], days: [1, 365] },
}

const mounted = []
const button = (w, text) => w.findAll('button').find((b) => b.text() === text)
async function render(component, options = {}) {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/', component, name: 'test' },
    { path: '/jobs/:jobId', component: JobView, name: 'job' },
    { path: '/drafts/:draftId', component: ReviewView, name: 'review' },
    { path: '/runs/:runId/report', component: { template: '<div />' }, name: 'report' },
  ] })
  await router.push(component === ReviewView ? '/drafts/phase1-new' : component === JobView ? '/jobs/job' : '/')
  const w = mount(component, { attachTo: document.body, global: { plugins: [router], stubs: { PageIntro: true, ScoutPanel: true } }, ...options })
  mounted.push(w)
  await flushPromises()
  return w
}

beforeEach(() => {
  vi.clearAllMocks()
  api.draft.mockResolvedValue(structuredClone(DRAFT))
  api.jobs.mockResolvedValue([])
  api.capabilities.mockResolvedValue([])
  api.job.mockResolvedValue({ id: 'job', kind: 'generate', draft: 'draft', state: 'succeeded', steps: [], progress: {}, log: ['第一行', '第二行'] })
  api.jobLive.mockResolvedValue({ personas: [], selected: null })
  api.jobShot.mockReturnValue('/shot.png')
  closeAllDrawers()
})

afterEach(() => {
  while (mounted.length) mounted.pop().unmount()
  settleConfirm(false)
  closeAllDrawers()
  vi.restoreAllMocks()
  vi.useRealTimers()
})

test('时间轴默认当天 24 小时窗口，随播放头移动并在两端限制范围，仍能切到全程', async () => {
  data.timeline.total = 7200
  const w = await render(SimTimeline, { props: { rows: true, pids: [], modelValue: 2400 } })
  expect(button(w, '当天').attributes('aria-pressed')).toBe('true')
  const state = w.vm.$.setupState
  expect(state.view).toEqual({ from: 1680, len: 1440 })
  await w.setProps({ modelValue: 4000 })
  expect(state.view).toEqual({ from: 3280, len: 1440 })
  await w.setProps({ modelValue: 0 })
  expect(state.view).toEqual({ from: 0, len: 1440 })
  await w.setProps({ modelValue: 7200 })
  expect(state.view).toEqual({ from: 5760, len: 1440 })
  await button(w, '全程').trigger('click')
  expect(state.view).toEqual({ from: 0, len: 7200 })
  await button(w, '2 小时').trigger('click')
  expect(state.view.len).toBe(120)
  await button(w, '30 分钟').trigger('click')
  expect(state.view.len).toBe(30)
  data.timeline.total = 600
  await button(w, '当天').trigger('click')
  expect(state.view).toEqual({ from: 0, len: 600 })
})

test.each([{ issues: [] }, { issues: ['性别变更', '参与方式变更'] }])('审核摘要显示人数、天数、模型与分布变更，并与底部批准条件一致：%j', async ({ issues }) => {
  const draft = reactive({ ...structuredClone(DRAFT), issues })
  api.draft.mockResolvedValue(draft)
  const w = await render(ReviewView)
  const summary = w.get('.approval-summary')
  expect(summary.text()).toContain('示例产品 · 2 人 · 1 天 · m')
  expect(summary.text()).toContain(issues.length ? '需确认 2 项分布变更' : '无需额外确认')
  const check = () => {
    for (const text of ['批准', '拒绝']) expect(button(summary, text).attributes('disabled')).toBe(button(w.get('.actions'), text).attributes('disabled'))
  }
  check()
  expect(button(summary, '批准').element.disabled).toBe(!!issues.length)
  if (issues.length) {
    await w.get('.ov input').setValue(true)
    check()
    expect(button(summary, '批准').element.disabled).toBe(false)
  }
  draft.blocked = '模型能力不符'
  await nextTick()
  check()
  expect(button(summary, '批准').element.disabled).toBe(true)
  expect(button(summary, '拒绝').element.disabled).toBe(false)
})

test('顶部批准沿用确认、哈希和 overrides，等待保存时两处同时禁用', async () => {
  api.draft.mockResolvedValue({ ...structuredClone(DRAFT), issues: ['参与方式变更'] })
  let finish
  api.decide.mockReturnValue(new Promise((resolve) => { finish = resolve }))
  const w = await render(ReviewView)
  await w.get('.ov input').setValue(true)
  await button(w.get('.approval-summary'), '批准').trigger('click')
  expect(api.decide).not.toHaveBeenCalled()
  settleConfirm(true)
  await flushPromises()
  expect(api.decide).toHaveBeenCalledWith('phase1-new', { decision: 'approve', draft_sha256: 'a'.repeat(64), accept_overrides: true })
  for (const scope of ['.approval-summary', '.actions']) {
    expect(button(w.get(scope), '批准').element.disabled).toBe(true)
    expect(button(w.get(scope), '拒绝').element.disabled).toBe(true)
  }
  finish({})
  await flushPromises()
})

test('批准后摘要与底部提供同一开始模拟操作；无效草稿不提供审批按钮', async () => {
  api.draft.mockResolvedValue({ ...structuredClone(DRAFT), status: 'approved', approval: { approved_at: '2026-10-15T12:00:00Z', overrides: [] } })
  api.simulate.mockResolvedValue({ id: 'job' })
  const w = await render(ReviewView)
  expect(w.get('.approval-summary b').text()).toBe('已批准')
  expect(button(w.get('.approval-summary'), '开始模拟').element.disabled).toBe(button(w.get('.actions'), '开始模拟').element.disabled)
  await button(w.get('.approval-summary'), '开始模拟').trigger('click')
  settleConfirm(true)
  await flushPromises()
  expect(api.simulate).toHaveBeenCalledWith('phase1-new')
  api.draft.mockResolvedValue({ status: 'pending', valid: false, error: '草稿无效' })
  const invalid = await render(ReviewView)
  expect(invalid.find('.approval-summary').exists()).toBe(false)
  expect(button(invalid, '批准')).toBeUndefined()
})

test('七项缺失默认折叠成一行，点查看恢复清单与首页提示', async () => {
  api.draft.mockResolvedValue({ ...structuredClone(DRAFT), material: { level: 'limited', summary: '资料很少，本次结果参考性有限', gaps: Array.from({ length: 7 }, (_, i) => ({ item: '资料' + i, effect: '影响' + i })) }, site: { status: 'failed', reason: 'HTTP 503' } })
  const w = await render(ReviewView)
  expect(w.get('.material-toggle').text()).toBe('资料很少，参考性有限 · 缺少 7 项 · 查看')
  expect(w.find('.material ul').exists()).toBe(false)
  await w.get('.material-toggle').trigger('click')
  expect(w.findAll('.material li')).toHaveLength(7)
  expect(w.get('.material').text()).toContain('首页没有读取成功（HTTP 503）')
  await w.get('.material-toggle').trigger('click')
  expect(w.find('.material ul').exists()).toBe(false)
})

test('功能仅列前五项，分布方案默认三行且有截断时可展开', async () => {
  vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(100)
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(40)
  const draft = structuredClone(DRAFT)
  draft.product.features = Array.from({ length: 8 }, (_, i) => '功能' + i)
  api.draft.mockResolvedValue(draft)
  const w = await render(ReviewView)
  expect(w.findAll('.feats li')).toHaveLength(5)
  expect(w.get('.rationale').classes()).toContain('clamped')
  await button(w, '显示全部 8 项功能').trigger('click')
  expect(w.findAll('.feats li')).toHaveLength(8)
  await button(w, '展开方案').trigger('click')
  expect(w.get('.rationale').classes()).not.toContain('clamped')
})

test('采样参数仅在展开行的高级区域出现，仍可修改保存', async () => {
  const w = await render(ReviewView)
  expect(w.get('thead').text()).not.toContain('top_p')
  expect(w.find('.sampling').exists()).toBe(false)
  expect(w.get('tbody').text()).not.toContain('0.7')
  await w.get('tr.click').trigger('click')
  expect(w.get('tr.detail').text()).toContain('高级')
  expect(w.get('.sampling').text()).toContain('presence_penalty 0.1')
  await button(w.get('.sampling'), '修改').trigger('click')
  await w.get('.sampling input').setValue(1.2)
  await button(w.get('.sampling'), '保存').trigger('click')
  await flushPromises()
  expect(api.editDraft).toHaveBeenCalledWith('phase1-new', { draft_sha256: 'a'.repeat(64), sampling: { p01: { temperature: 1.2, top_p: 0.9, presence_penalty: 0.1 } } })
  await w.get('tr.click').trigger('click')
  expect(w.find('.sampling').exists()).toBe(false)
})

test.each(['name', 'positioning', 'users'])('新建页补充信息默认收起；已有 %s 内容时自动展开，必填校验不受影响', async (field) => {
  const w = await render(NewRunView)
  expect(w.get('.optional').element.open).toBe(false)
  expect(w.get('.optional summary').text()).toBe('补充信息（可选）')
  expect(button(w, '检查').element.disabled).toBe(true)
  await w.get('[aria-label="产品网址"]').setValue('https://example.com')
  expect(w.get('[aria-label="允许访问的域名"]').element.value).toBe('example.com')
  expect(button(w, '检查').element.disabled).toBe(false)
  w.vm.$.setupState.form[field] = '已填内容'
  await nextTick()
  expect(w.get('.optional').element.open).toBe(true)
  const built = w.vm.$.setupState.built
  expect(built).toContain('已填内容')
  await w.get('.optional summary').trigger('click')
  await flushPromises()
  expect(w.get('.optional').element.open).toBe(false)
  await button(w, '完整说明书').trigger('click')
  await button(w, '只填网址').trigger('click')
  expect(w.get('.optional').element.open).toBe(true)
  expect(w.vm.$.setupState.built).toBe(built)
})

test.each(['running', 'succeeded', 'failed'])('任务日志默认收起，失败展开：%s', async (state) => {
  api.job.mockResolvedValue({ id: 'job', kind: 'generate', draft: 'draft', state, steps: [], progress: {}, log: ['第一行', '第二行'] })
  const w = await render(JobView)
  expect(w.get('.log-toggle').text()).toContain('日志 · 最近 2 行')
  expect(w.find('.log').exists()).toBe(state === 'failed')
  await w.get('.log-toggle').trigger('click')
  expect(w.find('.log').exists()).toBe(state !== 'failed')
})

test('轮询从运行中变成失败时，自动展开日志', async () => {
  vi.useFakeTimers()
  const job = { id: 'job', kind: 'generate', draft: 'draft', state: 'running', steps: [], progress: {}, log: ['进行中'] }
  api.job.mockResolvedValueOnce(job).mockResolvedValue({ ...job, state: 'failed', log: ['失败原因'] })
  const w = await render(JobView)
  expect(w.find('.log').exists()).toBe(false)
  await vi.advanceTimersByTimeAsync(2000)
  await flushPromises()
  expect(w.get('.log').text()).toBe('失败原因')
})

test('任务现场每个人物默认最近五步，切换人物后重置，仍可选中截图', async () => {
  api.job.mockResolvedValue({ id: 'job', kind: 'simulate', draft: 'draft', simulation: 'run', state: 'succeeded', steps: [], progress: {}, log: [] })
  const person = (id) => ({ id, name: id, state: 'completed', steps: Array.from({ length: 8 }, (_, i) => ({ n: i + 1, goal: '步骤' + i, actions: [], results: [], screenshot: 's' + i + '.png' })) })
  api.jobLive.mockResolvedValue({ personas: [person('p01'), person('p02')], selected: person('p01') })
  const w = await render(JobView)
  expect(w.findAll('.stepbtn')).toHaveLength(5)
  expect(w.findAll('.stepbtn .sn').map((s) => s.text())).toEqual(['8', '7', '6', '5', '4'])
  await button(w, '显示全部 8 步').trigger('click')
  expect(w.findAll('.stepbtn')).toHaveLength(8)
  await w.findAll('.stepbtn')[7].trigger('click')
  expect(w.get('.shot figcaption').text()).toContain('第 1 步')
  api.jobLive.mockResolvedValue({ personas: [person('p01'), person('p02')], selected: person('p02') })
  await w.findAll('.pill')[1].trigger('click')
  await flushPromises()
  expect(w.findAll('.stepbtn')).toHaveLength(5)
})

test('运行现场步骤、人物与动态默认五条，显示全部与切换人物仍可用', async () => {
  const adapted = adapt(structuredClone(sample))
  for (const [key, value] of Object.entries(adapted)) data.replaceAll(key === 'span' ? data.timeline : data[key], value)
  const first = data.personas[0]
  first.slot = data.timeline.total - 100
  // 扩充夹具，专门验证超过五条时的折叠与排序。
  const added = Array.from({ length: 6 }, (_, i) => ({ ...first, id: 'extra-' + i, realname: '新增人物' + i, slot: 100 + i }))
  data.personas.push(...added)
  for (const p of added) data.steps[p.id] = [{ ...data.steps[first.id][0], t: p.slot }]
  data.steps[first.id] = Array.from({ length: 8 }, (_, i) => ({ ...data.steps[first.id][0], n: i + 1, t: 200 + i }))
  const post = data.posts[0]
  data.posts.push(...Array.from({ length: 6 }, (_, i) => ({ ...post, id: 'extra-post-' + i, author: first.id, title: '新增帖子' + i, t: 300 + i, comments: [] })))
  rebuild()
  clock.t = data.timeline.total
  const w = await render(LiveView, { global: { stubs: { PageIntro: true, Shot: true, EmotionCurve: true, SimTimeline: true } } })
  expect(w.findAll('.log li')).toHaveLength(5)
  expect(w.findAll('.log .sn').map((s) => s.text())).toEqual(['#8', '#7', '#6', '#5', '#4'])
  expect(w.findAll('.feed li')).toHaveLength(5)
  expect(w.findAll('.people li')).toHaveLength(5)
  await button(w, '显示全部 8 步').trigger('click')
  expect(w.findAll('.log li')).toHaveLength(8)
  const feedCount = w.vm.$.setupState.feed.length
  await button(w, '显示全部 ' + feedCount + ' 条').trigger('click')
  expect(w.findAll('.feed li')).toHaveLength(feedCount)
  await button(w, '显示全部 ' + data.personas.length + ' 人').trigger('click')
  expect(w.findAll('.people li')).toHaveLength(data.personas.length)
  await w.get('[aria-label="查看 新增人物0 的实时画面"]').trigger('click')
  expect(w.findAll('.log li')).toHaveLength(1)
})

test('社区页使用的精简时间轴保留全程范围', async () => {
  data.timeline.total = 7200
  const w = await render(SimTimeline, { props: { pids: [], modelValue: 3600 } })
  expect(w.vm.$.setupState.view).toEqual({ from: 0, len: 7200 })
})

test('切换到另一失败任务时日志重新默认展开，切到成功任务时收起', async () => {
  const job = { id: 'job', kind: 'generate', draft: 'draft', state: 'failed', steps: [], progress: {}, log: ['失败原因'] }
  api.job.mockResolvedValue(job)
  const w = await render(JobView)
  await w.get('.log-toggle').trigger('click')
  expect(w.find('.log').exists()).toBe(false)
  api.job.mockResolvedValue({ ...job, id: 'next' })
  await w.vm.$router.push('/jobs/next')
  await flushPromises()
  expect(w.find('.log').exists()).toBe(true)
  api.job.mockResolvedValue({ ...job, id: 'done', state: 'succeeded' })
  await w.vm.$router.push('/jobs/done')
  await flushPromises()
  expect(w.find('.log').exists()).toBe(false)
})

test.each(['running', 'detached', 'succeeded'])('已批准草稿的模拟状态为 %s 时，隐藏摘要和所有模拟入口', async (state) => {
  api.draft.mockResolvedValue({ ...structuredClone(DRAFT), status: 'approved', simulations: ['phase4-done'], approval: { approved_at: '2026-10-15T12:00:00Z', overrides: [] } })
  api.jobs.mockResolvedValue([{ id: 'simulate-1', kind: 'simulate', draft: 'phase1-new', state, simulation: 'phase4-done', progress: { phase4_passed: true } }])
  const w = await render(ReviewView)
  expect(w.find('.approval-summary').exists()).toBe(false)
  expect(button(w, '开始模拟')).toBeUndefined()
  expect(button(w, '重新开始模拟')).toBeUndefined()
  expect(w.get('.flow a').text()).toBe(state === 'succeeded' ? '查看报告' : '查看模拟进度')
})

test('已有完成运行、没有任务记录的草稿也不显示摘要和模拟入口', async () => {
  api.draft.mockResolvedValue({ ...structuredClone(DRAFT), status: 'approved', simulations: ['phase4-done'], approval: { approved_at: '2026-10-15T12:00:00Z', overrides: [] } })
  const w = await render(ReviewView)
  expect(w.find('.approval-summary').exists()).toBe(false)
  expect(button(w, '开始模拟')).toBeUndefined()
  expect(w.get('.flow a').text()).toBe('查看报告')
})

test('上次模拟失败时顶部和底部共用重新开始模拟入口', async () => {
  api.draft.mockResolvedValue({ ...structuredClone(DRAFT), status: 'approved', approval: { approved_at: '2026-10-15T12:00:00Z', overrides: [] } })
  api.jobs.mockResolvedValue([{ id: 'simulate-1', kind: 'simulate', draft: 'phase1-new', state: 'failed', progress: {} }])
  api.simulate.mockResolvedValue({ id: 'job' })
  const w = await render(ReviewView)
  expect(w.get('.approval-summary b').text()).toBe('已批准 · 上次模拟没有完成')
  for (const scope of ['.approval-summary', '.actions']) expect(button(w.get(scope), '重新开始模拟').element.disabled).toBe(false)
  expect(button(w, '开始模拟')).toBeUndefined()
  await button(w.get('.approval-summary'), '重新开始模拟').trigger('click')
  expect(api.simulate).not.toHaveBeenCalled()
  settleConfirm(true)
  await flushPromises()
  expect(api.simulate).toHaveBeenCalledWith('phase1-new')
})

test('模拟任务状态尚未读完时不提前显示开始模拟入口', async () => {
  api.draft.mockResolvedValue({ ...structuredClone(DRAFT), status: 'approved', approval: { approved_at: '2026-10-15T12:00:00Z', overrides: [] } })
  let finish
  api.jobs.mockReturnValue(new Promise((resolve) => { finish = resolve }))
  const w = await render(ReviewView)
  expect(w.find('.approval-summary').exists()).toBe(false)
  expect(button(w, '开始模拟')).toBeUndefined()
  finish([{ id: 'simulate-1', kind: 'simulate', draft: 'phase1-new', state: 'running', progress: {} }])
  await flushPromises()
  expect(w.find('.approval-summary').exists()).toBe(false)
  expect(button(w, '开始模拟')).toBeUndefined()
  expect(w.get('.flow a').text()).toBe('查看模拟进度')
})
