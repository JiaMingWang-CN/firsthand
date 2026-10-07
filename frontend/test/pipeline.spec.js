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
      runs: call('runs', () => state.runs ?? []),
      checkManual: call('checkManual', (text) => (state.checkError ? new ApiError(422, state.checkError) : text.includes('---') ? state.checked : new ApiError(422, '说明书缺少 YAML front matter（开头和结尾的 ---）'))),
      capabilities: call('capabilities', () => state.capabilities),
      newDraft: call('newDraft', () => ({ id: 'prepare-1', draft: 'phase1-new' })),
      drafts: call('drafts', () => state.drafts),
      draft: call('draft', () => state.draft),
      resumeAnalysis: call('resumeAnalysis', () => ({ id: 'prepare-2', draft: 'phase1-new' })),
      generatePersonas: call('generatePersonas', () => ({ id: 'generate-1', draft: 'phase1-new' })),
      editDraft: call('editDraft', () => (state.editError ? state.editError : { draft_sha256: 'b'.repeat(64) })),
      decide: call('decide', (id, body) => { if (state.decideError) return state.decideError; state.draft = { ...state.draft, status: body.decision === 'approve' ? 'approved' : 'rejected', approval: { status: 'approved', approved_at: '2026-10-04T08:00:00Z', overrides: [] } }; return state.draft.approval }),
      simulate: call('simulate', () => ({ id: 'simulate-1' })),
      jobs: call('jobs', () => state.jobs),
      job: call('job', () => state.job),
      jobLive: call('jobLive', () => state.live),
      jobShot: (id, pid, name) => `/api/jobs/${id}/shots/${pid}/${name}`,
    },
  }
})

const { default: App } = await import('../src/App.vue')
const { router } = await import('../src/router.js')

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
const CONFIGURING = {
  id: 'phase1-new', status: 'configuring', valid: false, recommendation: { persona_count: 40, duration_days: 50, reason: '流程较少，取中间值' },
  minimum_personas: 3, limits: { personas: [2, 99], days: [1, 365] }, site: { status: 'failed', reason: 'HTTP 503' },
  material: { level: 'limited', summary: '资料很少，本次结果参考性有限：产品理解和人群分布主要来自 AI 推断', gaps: [{ item: '关键流程', effect: '没有指定任务，所有人自由探索' }] },
  product: { positioning: '作品展示', target_users: '招聘方', features: ['项目列表'], assumptions: ['定位由首页推断'] },
}
const CHECKED = {
  name: 'example.com', url: 'https://example.com/app', allowed_domains: ['example.com'], test_accounts: [], forbidden_actions: ['真实支付或下单'],
  flows: [], sections: [], known_issues: false, defaults: ['name', 'test_accounts', 'forbidden_actions'], minimum_personas: 2,
  material: { level: 'limited', summary: '资料很少，本次结果参考性有限：产品理解和人群分布主要来自 AI 推断',
    gaps: [{ item: 'test_accounts', effect: '只能以未登录的新访客身份体验' }, { item: '关键流程', effect: '没有指定任务，所有人自由探索' }] },
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
    checked: structuredClone(CHECKED), editError: null,
    capabilities: [{ id: 'phase0-mimo', created_at: '2026-10-04T00:00:00Z' }],
    draft: structuredClone(DRAFT), drafts: [], runs: [], jobs: [], job: null, decideError: null, checkError: null, live: { personas: [], selected: null },
  })
})
afterEach(() => { while (mounted.length) mounted.pop().unmount() })

test('新建运行：默认只填网址，域名随网址自动填好，检查后提示参考性；确认后按拼出的说明书分析，进入审核页', async () => {
  const w = await open('/new')
  await w.find('input[aria-label="产品网址"]').setValue('https://example.com/app')
  expect(w.find('input[aria-label="允许访问的域名"]').element.value).toBe('example.com')
  await button(w, '检查').trigger('click')
  await settle()
  const sent = calls.find(([name]) => name === 'checkManual')[1]
  expect(sent).toBe('---\nurl: "https://example.com/app"\nallowed_domains:\n  - "example.com"\n---\n')
  expect(w.find('.material').text()).toContain('参考性有限')
  expect(w.findAll('.checklist li.gap').map((li) => li.find('code').text())).toContain('# 关键流程')
  await button(w, '下一步：模型能力').trigger('click')
  await settle()
  expect(w.find('input[type="radio"]:checked').element.value).toBe('phase0-mimo')  // 默认复用最新的能力文件
  expect(w.text()).toContain('人物各自的温度、top_p 不会生效')  // 这份能力文件没探测采样参数
  await button(w, '下一步：分析资料').trigger('click')
  await button(w, '分析资料').trigger('click')
  await settle()
  expect(calls.some(([name]) => name === 'newDraft')).toBe(false)  // 先确认
  await confirm(w)
  expect(calls.find(([name]) => name === 'newDraft')).toEqual(['newDraft', sent, 'phase0-mimo'])
  await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe('/drafts/phase1-new'))  // 页面组件按需加载
})

test('新建运行：复用不支持识图的能力文件时，标出参考性有限，确认弹窗写明后才开始分析', async () => {
  state.capabilities = [{ id: 'phase0-text', created_at: '2026-10-04T00:00:00Z', sampling: true, vision: false }]
  const w = await open('/new')
  await w.find('input[aria-label="产品网址"]').setValue('https://example.com')
  await button(w, '检查').trigger('click')
  await settle()
  await button(w, '下一步：模型能力').trigger('click')
  await settle()
  expect(w.find('.cap').text()).toContain('不支持图像识别')
  await button(w, '下一步：分析资料').trigger('click')
  expect(w.find('.gen').text()).toContain('参考性有限')
  await button(w, '分析资料').trigger('click')
  await settle()
  expect(document.querySelector('.dlg').textContent).toContain('模型不支持图像识别')
  expect(calls.some(([name]) => name === 'newDraft')).toBe(false)
  await confirm(w)
  expect(calls.find(([name]) => name === 'newDraft')[2]).toBe('phase0-text')
})

test('探测发现模型不支持识图：分析暂停，提示参考性有限，点确认后才继续', async () => {
  state.draft = { id: 'phase1-new', status: 'text_only', text_only: true, valid: false, product: null, limits: { personas: [2, 99], days: [1, 365] } }
  const w = await open('/drafts/phase1-new')
  expect(w.find('.page-head').text()).toContain('参考性有限 · 纯文本模型')
  expect(w.text()).toContain('模型不支持图像识别')
  expect(w.text()).not.toContain('草稿未通过校验')
  await button(w, '接受并继续分析').trigger('click')
  await settle()
  expect(calls.some(([name]) => name === 'resumeAnalysis')).toBe(false)  // 先确认
  expect(document.querySelector('.dlg').textContent).toContain('参考性有限')
  state.draft = { ...structuredClone(CONFIGURING), text_only: true }
  await confirm(w)
  expect(calls.find(([name]) => name === 'resumeAnalysis')).toEqual(['resumeAnalysis', 'phase1-new'])
  expect(w.find('input[aria-label="人数"]').exists()).toBe(true)
  expect(w.text()).toContain('模型不支持图像识别')  // 继续后一直提示
})

test('运行列表：纯文本模型的草稿与运行都标注参考性有限', async () => {
  state.drafts = [{ id: 'phase1-text', status: 'text_only', product: '示例产品', text_only: true, created_at: '2026-10-04T00:00:00Z' }]
  state.runs = [{ id: 'phase4-text', passed: true, product: '示例产品', personas: 2, text_only: true, reports: [], started_at: null, finished_at: null },
    { id: 'phase4-vision', passed: true, product: '另一产品', personas: 2, text_only: false, reports: [], started_at: null, finished_at: null }]
  const w = await open('/')
  await settle()
  expect(w.find('.pipe').text()).toContain('模型不支持识图，待你确认是否继续')
  expect(w.find('.pipe').text()).toContain('参考性有限 · 纯文本模型')
  const rows = w.findAll('tbody tr')
  expect(rows.find((r) => r.text().includes('phase4-text')).text()).toContain('纯文本模型')
  expect(rows.find((r) => r.text().includes('phase4-vision')).text()).not.toContain('纯文本模型')
})

test('新建运行：选填的名称、定位、目标用户写进说明书；改过的域名不再跟着网址变', async () => {
  const w = await open('/new')
  await w.find('input[aria-label="允许访问的域名"]').setValue('a.example.com, b.example.com')
  await w.find('input[aria-label="产品网址"]').setValue('https://a.example.com')
  await w.find('input[aria-label="产品名称"]').setValue('作品集: 新版')
  await w.find('textarea[aria-label="产品定位"]').setValue('给招聘方看的作品集')
  await button(w, '检查').trigger('click')
  await settle()
  expect(calls.find(([name]) => name === 'checkManual')[1]).toBe(
    '---\nurl: "https://a.example.com"\nallowed_domains:\n  - "a.example.com"\n  - "b.example.com"\nname: "作品集: 新版"\n---\n\n# 产品定位\n\n给招聘方看的作品集\n')
})

test('新建运行：完整说明书模式下，校验前列出各项，未通过时标出报错点名的项', async () => {
  const w = await open('/new')
  await button(w, '完整说明书').trigger('click')
  expect(w.findAll('.checklist li.todo').length).toBe(10)
  await w.find('textarea').setValue('没有 front matter 的说明书')
  await button(w, '校验').trigger('click')
  await settle()
  expect(w.find('[role="alert"]').text()).toContain('缺少 YAML front matter')
  state.checkError = 'allowed_domains: Field required'
  await w.find('textarea').setValue('---\nurl: https://example.com\n---\n')
  await button(w, '校验').trigger('click')
  await settle()
  expect(w.findAll('.checklist li.bad').map((li) => li.find('code').text())).toEqual(['allowed_domains'])
  expect(button(w, '下一步：模型能力')).toBeUndefined()
})

test('新建运行：没有可复用的能力文件时说明探测发生在分析时，按钮与确认弹窗都写明会先探测', async () => {
  state.capabilities = []
  const w = await open('/new')
  await w.find('input[aria-label="产品网址"]').setValue('https://example.com')
  await button(w, '检查').trigger('click')
  await settle()
  await button(w, '下一步：模型能力').trigger('click')
  await settle()
  expect(w.find('.note').text()).toContain('探测不在这一步执行')
  await button(w, '下一步：分析资料').trigger('click')
  expect(w.findAll('button').some((b) => b.text() === '分析资料')).toBe(false)
  await button(w, '探测模型能力并分析资料').trigger('click')
  await settle()
  expect(document.querySelector('.dlg').textContent).toContain('先探测模型能力')
  await confirm(w)
  expect(calls.find(([name]) => name === 'newDraft')[2]).toBe('')
})

test('确认人数与天数：显示推荐与参考性提示，可修改，低于下限时不能生成，确认后按所填数字生成', async () => {
  state.draft = structuredClone(CONFIGURING)
  const w = await open('/drafts/phase1-new')
  expect(w.find('.material').text()).toContain('参考性有限')
  expect(w.find('.material').text()).toContain('首页没有读取成功（HTTP 503）')
  expect(w.text()).toContain('推荐 40 人、50 天')
  const count = w.find('input[aria-label="人数"]'), days = w.find('input[aria-label="天数"]')
  expect([count.element.value, days.element.value]).toEqual(['40', '50'])
  await count.setValue(2)
  expect(w.find('.size [role="alert"]').text()).toContain('至少需要 3 人')
  expect(button(w, '生成人物').attributes('disabled')).toBeDefined()
  await count.setValue(45)
  await button(w, '生成人物').trigger('click')
  await settle()
  expect(document.querySelector('.dlg').textContent).toContain('45 人')
  await confirm(w)
  expect(calls.find(([name]) => name === 'generatePersonas')).toEqual(['generatePersonas', 'phase1-new', 45, 50])
})

test('审核：可改天数（不能少于最晚的体验日）和每个人的采样参数，带上展示版本的哈希', async () => {
  state.draft.run_config.duration_days = 3
  const w = await open('/drafts/phase1-new')
  expect(w.text()).toContain('第 2 天')
  expect(w.text()).toContain('0.7 / 0.9')
  const days = w.find('input[aria-label="模拟天数"]')
  await days.setValue(1)
  expect(w.text()).toContain('有人排在第 2 天首次体验')
  expect(button(w, '保存天数').attributes('disabled')).toBeDefined()
  await days.setValue(7)
  await button(w, '保存天数').trigger('click')
  await settle()
  expect(calls.find(([name]) => name === 'editDraft')).toEqual(['editDraft', 'phase1-new', { draft_sha256: 'a'.repeat(64), duration_days: 7 }])
  await w.findAll('tr.click')[0].trigger('click')
  await button(w, '修改').trigger('click')
  await w.find('.sampling input').setValue(1.25)
  await button(w, '保存').trigger('click')
  await settle()
  expect(calls.filter(([name]) => name === 'editDraft').at(-1)[2]).toEqual(
    { draft_sha256: 'a'.repeat(64), sampling: { p01: { temperature: 1.25, top_p: 0.9, presence_penalty: 0.1 } } })
})

test('审核：能力文件没探测采样参数时说明人物各自的参数不会生效', async () => {
  state.draft.sampling = { probed: false, chat: false, configured_api: false, thinking: null }
  const w = await open('/drafts/phase1-new')
  expect(w.find('.pad-note').text()).toContain('不会发送人物各自的温度')
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

test('任务页：现场显示正在浏览的人物、步骤与最新截图，可切换人物，只在浏览中给 Steel 链接', async () => {
  const running = { id: 'p02', name: '乙', profession: '设计师', age: 30, city: '上海', state: 'running', local_time: '2026-10-05T10:10:00+08:00', viewer_url: 'https://app.steel.dev/sessions/abc',
    steps: [{ n: 1, eval: '首页加载成功。', memory: '读到姓名', goal: '点击全部项目', actions: ['click index: 26'], results: ['Clicked'], screenshot: 's001_after.png' },
      { n: 2, eval: '进入列表页。', memory: '', goal: '向下滚动', actions: ['scroll down'], results: [], screenshot: null }] }
  state.job = { id: 'simulate-1', kind: 'simulate', state: 'running', draft: 'phase1-new', simulation: 'phase4-x', report: 'phase5-x', created_at: '2026-10-05T02:00:00Z',
    steps: [{ name: '体验与社区讨论（阶段 4）', state: 'running' }], progress: { slices_done: 1, slices: 24, personas: 2, personas_done: 1, personas_failed: 0 }, log: [] }
  state.live = { personas: [{ id: 'p01', name: '甲', state: 'completed' }, { id: 'p02', name: '乙', state: 'running' }], selected: running }
  const w = await open('/jobs/simulate-1')
  const watch = w.find('.watch')
  expect(watch.text()).toContain('乙')
  expect(watch.find('img').attributes('src')).toBe('/api/jobs/simulate-1/shots/p02/s001_after.png')  // 第 2 步还没有截图，显示最近一张
  expect(watch.find('.shot figcaption').text()).toContain('第 1 步')
  expect(watch.findAll('.steplist > li').map((li) => li.find('.sn').text())).toEqual(['2', '1'])  // 最新的在最上面
  expect(watch.find('a[href="https://app.steel.dev/sessions/abc"]').attributes('rel')).toContain('noopener')
  state.live = { ...state.live, selected: { ...running, id: 'p01', name: '甲', state: 'completed', viewer_url: null } }
  await watch.findAll('.pill')[0].trigger('click')
  await settle()
  expect(calls.filter(([name]) => name === 'jobLive').at(-1)).toEqual(['jobLive', 'simulate-1', 'p01'])
  expect(w.findAll('.watch a').some((a) => a.text().includes('Steel'))).toBe(false)
})

test('运行列表：显示进行中的任务和待审核的草稿', async () => {
  state.jobs = [{ id: 'simulate-1', kind: 'simulate', state: 'running', progress: { slices_done: 2, slices: 24, personas_done: 1, personas: 10 } }]
  state.drafts = [{ id: 'phase1-new', status: 'pending', product: '示例产品' }, { id: 'phase1-old', status: 'approved', product: '旧产品', simulated: true },
    { id: 'phase1-ready', status: 'approved', product: '待模拟产品', simulated: false }]
  const w = await open('/runs')
  const text = w.find('.pipe').text()
  expect(text).toContain('时间片 2/24')
  expect(text).toContain('示例产品')
  expect(text).toContain('待你审核批准')
  expect(text).not.toContain('旧产品')  // 已经模拟过的草稿不再算“进行中”
  expect(text).toContain('待模拟产品')  // 批准了还没开始模拟：下一步是开始模拟
  expect(text).toContain('已批准，待开始模拟')
})

test('流程条：每一页都说明做到第几步、已完成什么、下一步做什么，并给出下一步的按钮', async () => {
  const flow = (w) => w.find('.flow')
  const current = (w) => flow(w).find('[aria-current="step"]').text()
  let w = await open('/new')
  expect(current(w)).toContain('填写资料')
  expect(flow(w).text()).toContain('第 1/7 步')

  state.draft = { ...structuredClone(CONFIGURING), status: 'analyzing' }
  w = await open('/drafts/phase1-new')
  expect(current(w)).toContain('分析资料')
  expect(flow(w).text()).toContain('不需要操作')

  state.draft = structuredClone(CONFIGURING)
  w = await open('/drafts/phase1-new')
  expect(current(w)).toContain('确认人数与天数')
  expect(flow(w).text()).toContain('生成人物')
  expect(flow(w).findAll('li.done').length).toBe(2)

  state.draft = structuredClone(DRAFT)
  w = await open('/drafts/phase1-new')
  expect(current(w)).toContain('审核批准')
  expect(flow(w).find('button').text()).toBe('前往审核区')

  state.draft = { ...structuredClone(DRAFT), status: 'approved', approval: { status: 'approved', approved_at: '2026-10-04T08:00:00Z', overrides: [] } }
  w = await open('/drafts/phase1-new')
  expect(current(w)).toContain('模拟体验与讨论')
  await flow(w).find('button').trigger('click')
  await confirm(w)
  expect(calls.some(([name]) => name === 'simulate')).toBe(true)

  state.jobs = [{ id: 'simulate-1', kind: 'simulate', state: 'running', draft: 'phase1-new', simulation: 'phase4-x', progress: { personas_done: 3, personas: 10, phase4_passed: null } }]
  w = await open('/drafts/phase1-new')
  expect(flow(w).text()).toContain('3/10')
  expect(flow(w).find('a').attributes('href')).toBe('#/jobs/simulate-1')

  state.jobs = [{ ...state.jobs[0], state: 'succeeded', progress: { phase4_passed: true } }]
  w = await open('/drafts/phase1-new')
  expect(flow(w).text()).toContain('全部完成')
  expect(flow(w).find('a').attributes('href')).toBe('#/runs/phase4-x/report')
})

test('流程条：任务页结束后指向下一步——分析完去确认人数，生成失败回草稿重试', async () => {
  const base = { draft: 'phase1-new', created_at: '2026-10-04T08:00:00Z', steps: [], log: [] }
  state.job = { ...base, id: 'prepare-1', kind: 'prepare', state: 'succeeded', progress: { capability: true, site: true, product: true } }
  let w = await open('/jobs/prepare-1')
  expect(w.find('.flow [aria-current="step"]').text()).toContain('确认人数与天数')
  expect(w.find('.flow a').text()).toBe('去确认人数与天数')
  state.job = { ...base, id: 'generate-1', kind: 'generate', state: 'failed', progress: { draft: false } }
  w = await open('/jobs/generate-1')
  expect(w.find('.flow li.failed').text()).toContain('生成人物')
  expect(w.find('.flow a').attributes('href')).toBe('#/drafts/phase1-new')
})
