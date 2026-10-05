// 新建运行、运行前审核、任务进度：HTTP 层换成桩，走真实的路由、页面与确认弹窗。
import { test, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const calls = vi.hoisted(() => [])
const state = vi.hoisted(() => ({}))

vi.mock('../src/api/client.js', async (importOriginal) => {
  const { ApiError } = await importOriginal()
  const call = (name, value) => async (...args) => {
    calls.push([name, ...args])
    const result = typeof value === 'function' ? value(...args) : value
    if (result instanceof Error) throw result
    return structuredClone(result)
  }
  return {
    ApiError,
    api: {
      runs: call('runs', () => []),
      checkManual: call('checkManual', (text) => (text.includes('---') ? state.checked : new ApiError(422, '说明书缺少 YAML front matter（开头和结尾的 ---）'))),
      capabilities: call('capabilities', () => state.capabilities),
      newDraft: call('newDraft', () => ({ id: 'prepare-1', draft: 'phase1-new' })),
      drafts: call('drafts', () => state.drafts),
      draft: call('draft', () => state.draft),
      decide: call('decide', (id, body) => { if (state.decideError) return state.decideError; state.draft = { ...state.draft, status: body.decision === 'approve' ? 'approved' : 'rejected', approval: { status: 'approved', approved_at: '2026-10-04T08:00:00Z', overrides: [] } }; return state.draft.approval }),
      simulate: call('simulate', () => ({ id: 'simulate-1' })),
      jobs: call('jobs', () => state.jobs),
      job: call('job', () => state.job),
    },
  }
})

const { default: App } = await import('../src/App.vue')
const { router } = await import('../src/router.js')

const PERSONA = (i) => ({
  persona_id: `p0${i}`, realname: `人物${i}`, age: 30, gender: '女', profession: '设计师', city: '上海', timezone: 'Asia/Shanghai', bio: '简介',
  persona: '叙述', participation: 'poster', browsing_profile: { device: 'mobile', tech_level: 'novice', patience: 'low', motivation: '随便看看',
    assignment: { type: 'explore', flow: null }, tools: [], max_steps: 30 },
  schedule: { wake: '07:00', sleep: '23:00', state_at_browse: '通勤路上' }, disclosure: { candor: '中', withhold_tendency: '高', withhold_reasons: ['怕显得不会用'] },
})
const DRAFT = {
  id: 'phase1-new', status: 'pending', valid: true, draft_sha256: 'a'.repeat(64), approval: { status: 'pending' },
  manual: { name: '示例产品', url: 'https://example.com', flows: ['注册'] }, product: { positioning: '定位', target_users: '用户', features: ['功能'] },
  run_config: { start_time: '2026-10-03T00:00:00Z', duration_days: 1, time_slice_minutes: 60, max_concurrency: 5 }, cohort_rationale: '分布说明',
  personas: [PERSONA(1), PERSONA(2)], schedule: [{ persona_id: 'p01', local_time: '2026-10-03T09:40:00+08:00', slice_index: 1 }, { persona_id: 'p02', local_time: '2026-10-03T21:10:00+08:00', slice_index: 13 }],
  distribution: ['- 性别：女 2'], issues: [], capability: { model: 'm' }, simulations: [],
}

const mounted = []
async function open(path) {
  await router.push(path)
  const w = mount(App, { global: { plugins: [router] }, attachTo: document.body })
  mounted.push(w)
  await router.isReady()
  await settle()
  return w
}
const settle = async () => { for (let i = 0; i < 6; i++) await flushPromises() }
const confirm = async (w) => { await w.find('.dlg .btn-primary, .dlg .btn-danger').trigger('click'); await settle() }
const button = (w, text) => w.findAll('button').find((b) => b.text().includes(text))

beforeEach(() => {
  calls.length = 0
  Object.assign(state, {
    checked: { name: '示例产品', url: 'https://example.com', allowed_domains: ['example.com'], test_accounts: ['new_visitor'], forbidden_actions: 2, flows: [{ name: '注册', account_role: 'new_visitor' }], sections: [], known_issues: true },
    capabilities: [{ id: 'phase0-mimo', created_at: '2026-10-04T00:00:00Z' }],
    draft: structuredClone(DRAFT), drafts: [], jobs: [], job: null, decideError: null,
  })
})
afterEach(() => { while (mounted.length) mounted.pop().unmount() })

test('新建运行：校验不通过时说明原因；通过后复用能力文件并在确认后生成，进入审核页', async () => {
  const w = await open('/new')
  await w.find('textarea').setValue('没有 front matter 的说明书')
  await button(w, '校验').trigger('click')
  await settle()
  expect(w.find('[role="alert"]').text()).toContain('缺少 YAML front matter')
  await w.find('textarea').setValue('---\nname: x\n---\n')
  await button(w, '校验').trigger('click')
  await settle()
  expect(w.text()).toContain('校验通过')
  await button(w, '下一步：模型能力').trigger('click')
  await settle()
  expect(w.find('input[type="radio"]:checked').element.value).toBe('phase0-mimo')  // 默认复用最新的能力文件
  await button(w, '下一步：生成人物').trigger('click')
  await button(w, '生成人物草稿').trigger('click')
  await settle()
  expect(calls.some(([name]) => name === 'newDraft')).toBe(false)  // 先确认
  await confirm(w)
  expect(calls.find(([name]) => name === 'newDraft')).toEqual(['newDraft', '---\nname: x\n---\n', 'phase0-mimo'])
  await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe('/drafts/phase1-new'))  // 页面组件按需加载
})

test('审核：批准时带上展示版本的哈希；分布变更须勾选确认；批准后可开始模拟并跳到任务页', async () => {
  state.draft.issues = ['参与方式：poster 3（规划 2）']
  const w = await open('/drafts/phase1-new')
  expect(w.text()).toContain('人物1')
  const approve = () => button(w, '批准')
  expect(approve().attributes('disabled')).toBeDefined()
  await w.find('.ov input').setValue(true)
  expect(approve().attributes('disabled')).toBeUndefined()
  await approve().trigger('click')
  await confirm(w)
  expect(calls.find(([name]) => name === 'decide')).toEqual(['decide', 'phase1-new', { decision: 'approve', draft_sha256: 'a'.repeat(64), accept_overrides: true }])
  expect(w.text()).toContain('已批准')
  await button(w, '开始模拟').trigger('click')
  await confirm(w)
  expect(calls.some(([name]) => name === 'simulate')).toBe(true)
  await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe('/jobs/simulate-1'))  // 页面组件按需加载
})

test('审核：后端拒绝时显示原因（例如展示后草稿被改过）', async () => {
  const { ApiError } = await import('../src/api/client.js')
  state.decideError = new ApiError(422, '草稿与刚才展示的版本不同，请先重新加载后再批准')
  const w = await open('/drafts/phase1-new')
  await button(w, '批准').trigger('click')
  await confirm(w)
  expect(w.find('.actions [role="alert"]').text()).toContain('请先重新加载')
})

test('审核：能力文件与当前模型配置不符时先说明原因，批准不可点', async () => {
  state.draft.blocked = '这份草稿生成时用的模型能力文件与当前模型配置不符或已过期，批准会被拒绝。请重新新建运行（重新探测模型能力）。'
  const w = await open('/drafts/phase1-new')
  expect(w.find('.warn.block').text()).toContain('重新新建运行')
  expect(button(w, '批准').attributes('disabled')).toBeDefined()
  expect(button(w, '拒绝').attributes('disabled')).toBeUndefined()
})

test('审核：手工改坏的草稿只显示原因，不提供批准', async () => {
  state.draft = { id: 'phase1-new', status: 'pending', valid: false, error: 'Only developers can use technical tools' }
  const w = await open('/drafts/phase1-new')
  expect(w.text()).toContain('Only developers')
  expect(button(w, '批准')).toBeUndefined()
})

test('审核：生成中显示进度与日志，生成失败给出错误类型', async () => {
  state.draft = { id: 'phase1-new', status: 'failed', valid: false, error: { type: 'RateLimitError', status_code: 429 } }
  state.jobs = [{ id: 'prepare-1', kind: 'prepare', draft: 'phase1-new', state: 'failed' }]
  state.job = { id: 'prepare-1', kind: 'prepare', draft: 'phase1-new', state: 'failed', progress: { capability: true, draft: false }, log: ['阶段 1 失败：RateLimitError'] }
  const w = await open('/drafts/phase1-new')
  expect(w.text()).toContain('RateLimitError（HTTP 429）')
  expect(w.find('.log').text()).toContain('阶段 1 失败')
})

test('任务页：按运行目录显示时间片与人物进度，阶段 4 写出结果后可打开运行', async () => {
  state.job = { id: 'simulate-1', kind: 'simulate', state: 'running', draft: 'phase1-new', simulation: 'phase4-x', report: 'phase5-x', created_at: '2026-10-04T08:00:00Z',
    steps: [{ name: '体验与社区讨论（阶段 4）', state: 'running' }, { name: '生成报告（阶段 5）', state: 'pending' }],
    progress: { slices_done: 6, slices: 24, personas: 10, personas_done: 3, personas_failed: 1, phase4_passed: null, report_passed: null }, log: ['时间片 5 讨论完成'] }
  const w = await open('/jobs/simulate-1')
  expect(w.text()).toContain('6/24')
  expect(w.text()).toContain('3/10')
  expect(w.text()).toContain('失败 1')
  expect(button(w, '打开这次运行')).toBeUndefined()
  expect(w.findAll('a').some((a) => a.text() === '打开这次运行')).toBe(false)
  state.job = { ...state.job, state: 'succeeded', progress: { ...state.job.progress, phase4_passed: true, report_passed: true } }
  await new Promise((r) => setTimeout(r, 2100))
  await settle()
  expect(w.findAll('a').find((a) => a.text() === '打开这次运行').attributes('href')).toBe('#/runs/phase4-x/report')
})

test('运行列表：显示进行中的任务和待审核的草稿', async () => {
  state.jobs = [{ id: 'simulate-1', kind: 'simulate', state: 'running', progress: { slices_done: 2, slices: 24, personas_done: 1, personas: 10 } }]
  state.drafts = [{ id: 'phase1-new', status: 'pending', product: '示例产品' }, { id: 'phase1-old', status: 'approved', product: '旧产品' }]
  const w = await open('/runs')
  const text = w.find('.pipe').text()
  expect(text).toContain('时间片 2/24')
  expect(text).toContain('示例产品')
  expect(text).not.toContain('旧产品')
})
