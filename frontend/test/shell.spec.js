// 阶段 A：外壳导航、页头介绍与浮层快捷键；页面内容用桩，路由元数据沿用真实配置。
import { test, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, shallowMount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { nextTick } from 'vue'
import App from '../src/App.vue'
import AppNav from '../src/components/AppNav.vue'
import PageIntro from '../src/components/PageIntro.vue'
import { router as appRouter } from '../src/router.js'
import { live, run, product, timeline, personas } from '../src/lib/data.js'
import { clock, pause, seek, drawers, openDrawer, closeAllDrawers } from '../src/lib/store.js'
import { flowState } from '../src/lib/shell.js'
import { usageTip } from '../src/lib/usage.js'
import * as data from '../src/lib/data.js'
import { adapt } from '../src/api/adapt.js'
import { api } from '../src/api/client.js'
import { rebuild } from '../src/lib/sim.js'
import sample from './fixtures/sample.json'

vi.mock('../src/lib/live.js', () => ({ ensureRun: vi.fn() }))

let router, wrapper
beforeEach(() => {
  localStorage.clear()
  router = createRouter({
    history: createMemoryHistory(),
    routes: appRouter.getRoutes().filter((r) => r.name).map((r) => ({
      path: r.path, name: r.name, meta: r.meta, component: { template: '<div class="page">页面数据</div>' },
    })),
  })
  Object.assign(live, { id: 'run-a', status: 'ready' })
  Object.assign(product, { name: '示例产品' })
  Object.assign(timeline, { total: 7200, sliceMinutes: 60, startMs: 0 })
  Object.assign(run, {
    id: 'run-a', report: { id: 'report-a' }, model: 'provider / model',
    startedAt: '2026-10-01T00:00:00Z', endedAt: '2026-10-02T00:00:00Z', concurrency: 10,
    usage: { total: { requests: 733, input_tokens: 1000, cached_input_tokens: 200, output_tokens: 300 },
      models: [{ model: 'model', input_tokens: 1000, cached_input_tokens: 200, output_tokens: 300 }] },
    interviewUsage: { total: { requests: 2, input_tokens: 50, cached_input_tokens: 0, output_tokens: 10 } },
  })
  personas.length = 0
  flowState.at = null
  flowState.done = false
  clock.t = 600
  pause()
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  pause()
  closeAllDrawers()
  vi.restoreAllMocks()
  localStorage.clear()
})

async function open(page, component = App) {
  await router.push(page)
  wrapper = mount(component, { attachTo: document.body, global: {
    plugins: [router], stubs: { DrawerHost: true, ConfirmDialog: true, ToastHost: true },
  } })
  await flushPromises()
  return wrapper
}
function key(target, value) {
  target.dispatchEvent(new KeyboardEvent('keydown', { key: value, bubbles: true, cancelable: true }))
}

test.each(['live', 'community', 'report', 'personas', 'interview'])('%s 仅按路由配置显示状态栏与响应空格播放', async (name) => {
  await open('/runs/run-a/' + name)
  const playable = ['live', 'community'].includes(name)
  expect(wrapper.find('.runbar').exists()).toBe(playable)
  key(document.body, ' ')
  expect(clock.playing).toBe(playable)
  expect(wrapper.find('.folio').exists()).toBe(false)
  expect(wrapper.find('.bignum').exists()).toBe(false)
})

test('人物页仍从 ?t= 读取时刻，并把后续时刻写回链接', async () => {
  await open('/runs/run-a/personas?t=D1-09:00')
  expect(router.currentRoute.value.meta.timeLinked).toBe(true)
  expect(clock.t).toBe(540)
  seek(620)
  await nextTick()
  await new Promise((resolve) => setTimeout(resolve, 200))
  await flushPromises()
  expect(router.currentRoute.value.query.t).toBe('D1-10:20')
  expect(wrapper.find('.runbar').exists()).toBe(false)
})

test.each([['模拟', 'live'], ['报告', 'report'], ['采访', 'interview']])('有运行时流程中的%s可点击跳转', async (label, name) => {
  await open('/runs/run-a/report?t=D1-09:00', AppNav)
  expect(wrapper.findAll('.rsteps li')).toHaveLength(4)
  const links = wrapper.findAll('.rsteps a')
  expect(links).toHaveLength(3)
  await links.find((a) => a.text() === label).trigger('click')
  await flushPromises()
  expect(router.currentRoute.value.name).toBe(name)
  expect(router.currentRoute.value.params.runId).toBe('run-a')
  expect(router.currentRoute.value.query.t).toBe(name === 'live' ? 'D1-09:00' : undefined)
  expect(wrapper.findAll('.extra-links a').map((a) => a.text())).toEqual(['人物', '社区'])
})

test.each(['/runs', '/new', '/drafts/draft-a', '/jobs/job-a'])('无运行时 %s 八步流程完整且只读', async (path) => {
  await open(path, AppNav)
  expect(wrapper.findAll('.rsteps li')).toHaveLength(8)
  expect(wrapper.findAll('.rsteps a')).toHaveLength(0)
  expect(wrapper.find('.prep').exists()).toBe(false)
  expect(wrapper.findAll('.rsteps li').map((li) => li.text())).toEqual([
    '01资料', '02分析', '03人数与天数', '04生成人物', '05审核', '06模拟', '07报告', '08采访',
  ])
  expect(wrapper.find('.cur').exists()).toBe(false)
})

test('页头介绍按路由名记住关闭，不影响其他页', async () => {
  await open('/runs/run-a/report', PageIntro)
  await wrapper.get('button').trigger('click')
  expect(wrapper.find('.page-intro').exists()).toBe(false)
  wrapper.unmount()
  await router.push('/runs/run-a/report')
  wrapper = mount(PageIntro, { global: { plugins: [router] } })
  expect(wrapper.find('.page-intro').exists()).toBe(false)
  await router.push('/runs/run-a/live')
  expect(wrapper.find('.page-intro').exists()).toBe(true)
  await router.push('/runs/run-a/report')
  expect(wrapper.find('.page-intro').exists()).toBe(false)
  await router.push('/runs/run-b/report')
  expect(wrapper.find('.page-intro').exists()).toBe(false)
})

test('localStorage 读取或写入失败时介绍照常显示', async () => {
  vi.spyOn(localStorage, 'getItem').mockImplementation(() => { throw new Error('存储被禁用') })
  vi.spyOn(localStorage, 'setItem').mockImplementation(() => { throw new Error('存储被禁用') })
  await open('/runs/run-a/report', PageIntro)
  expect(wrapper.find('.page-intro').exists()).toBe(true)
  await wrapper.get('button').trigger('click')
  expect(wrapper.find('.page-intro').exists()).toBe(true)
})

test('用量仅显示请求数，完整明细与总量在提示和运行详情中一致', async () => {
  await open('/runs/run-a/live')
  const cost = wrapper.get('.cost')
  expect(cost.text()).toBe('用量733 次请求')
  expect(cost.attributes('title')).toBe(usageTip.value)
  expect(cost.attributes('title')).toContain('全程 733 次请求（model）：输入 1,000（缓存 200）· 输出 300')
  expect(cost.attributes('title')).toContain('采访另计 2 次请求')
  expect(cost.attributes('title').split('\n')).toHaveLength(2)
  expect(cost.attributes('title').match(/model/g)).toHaveLength(1)
  expect(wrapper.get('.rmeta').text()).toContain('0 人 · 5 天')
  expect(wrapper.get('.rmeta').text()).not.toContain('run-a')
  await wrapper.get('.product-line button').trigger('click')
  const dialog = document.querySelector('dialog')
  expect(dialog.open).toBe(true)
  expect(dialog.textContent).toContain('运行详情')
  for (const value of ['run-a', 'report-a', 'provider / model', '60 分钟', '10', usageTip.value]) {
    expect(dialog.textContent).toContain(value)
  }
  // 模拟播放时 URL 时刻的变化不应把正在阅读的详情关掉。
  await router.replace({ query: { t: 'D1-10:00' } })
  expect(dialog.open).toBe(true)
})

test('快捷键默认收起，按钮与 ? 可打开，Escape 仅关闭浮层', async () => {
  await open('/runs/run-a/live')
  const dialog = document.querySelector('dialog')
  expect(dialog.open).toBe(false)
  const help = wrapper.findAll('.rfoot button').find((b) => b.text() === '? 快捷键')
  await help.trigger('click')
  expect(dialog.open).toBe(true)
  expect(dialog.textContent).toContain('切换报告问题')
  openDrawer({ type: 'persona', pid: 'p01' })
  key(dialog.querySelector('button'), ' ')
  expect(clock.playing).toBe(false)
  key(dialog, 'Escape')
  expect(dialog.open).toBe(false)
  expect(drawers.stack).toHaveLength(1)
  key(document.body, 'Escape')
  expect(drawers.stack).toHaveLength(0)
  key(document.body, '?')
  await nextTick()
  expect(dialog.open).toBe(true)
  key(dialog, '?')
  expect(dialog.open).toBe(false)
})

test('输入文字时 ? 不触发快捷键，切换页面关闭运行详情', async () => {
  await open('/runs/run-a/report')
  const input = document.createElement('input')
  document.body.append(input)
  key(input, '?')
  input.remove()
  const dialog = document.querySelector('dialog')
  expect(dialog.open).toBe(false)
  await wrapper.get('.product-line button').trigger('click')
  await router.push('/runs')
  expect(dialog.open).toBe(false)
})

test.each(['live', 'report', 'interview', 'personas', 'community'])('已有运行的 %s 折叠准备步骤，人物社区紧跟采访', async (page) => {
  await open('/runs/run-a/' + page + '?t=D1-09:00', AppNav)
  const prep = wrapper.get('.rsteps .prep')
  expect(prep.text()).toBe('01–05 准备')
  expect(prep.classes()).toContain('done')
  expect(prep.find('a').exists()).toBe(false)
  expect(wrapper.findAll('.rsteps li')).toHaveLength(4)
  expect(wrapper.findAll('.rsteps .no').map((n) => n.text())).toEqual(['01–05', '06', '07', '08'])
  expect(wrapper.findAll('.rflow a').map((a) => a.text())).toEqual(['模拟', '报告', '采访', '人物', '社区'])
  expect(wrapper.get('.rsteps').element.nextElementSibling).toBe(wrapper.get('.extra-links').element)
  expect(wrapper.get('.rsteps a').attributes('title')).toBe('运行现场')
  if (['personas', 'community'].includes(page)) {
    expect(wrapper.get('.extra-links a.on').text()).toBe(page === 'personas' ? '人物' : '社区')
  }
})

test.each([['人物', 'personas'], ['社区', 'community']])('已有运行的%s链接保留模拟时刻', async (label, page) => {
  await open('/runs/run-a/report?t=D1-09:00', AppNav)
  await wrapper.findAll('.extra-links a').find((a) => a.text() === label).trigger('click')
  await flushPromises()
  expect(router.currentRoute.value.name).toBe(page)
  expect(router.currentRoute.value.params.runId).toBe('run-a')
  expect(router.currentRoute.value.query.t).toBe('D1-09:00')
})

test('多个模型显示全程汇总和逐模型明细，详情与状态栏保持一致', async () => {
  run.usage.models.push({ model: '另一个模型', input_tokens: 400, cached_input_tokens: 100, output_tokens: 50 })
  Object.assign(run.usage.total, { requests: 740, input_tokens: 1400, cached_input_tokens: 300, output_tokens: 350 })
  await open('/runs/run-a/live')
  const tip = wrapper.get('.cost').attributes('title')
  expect(tip.split('\n')).toEqual([
    '全程 740 次请求：输入 1,400（缓存 300）· 输出 350',
    'model：输入 1,000（缓存 200）· 输出 300',
    '另一个模型：输入 400（缓存 100）· 输出 50',
    '采访另计 2 次请求：输入 50（缓存 0）· 输出 10',
  ])
  await wrapper.get('.product-line button').trigger('click')
  expect(document.querySelector('dialog .usage').textContent).toBe(tip)
})

test.each([
  ['community', '/runs/run-a/community', '社区'],
  ['personas', '/runs/run-a/personas', '人物'],
  ['live', '/runs/run-a/live', '运行现场'],
  ['interview', '/runs/run-a/interview', '采访'],
  ['new', '/new', '新建运行'],
])('%s 页头保留标题并去掉重复 eyebrow', async (name, path, title) => {
  const model = adapt(structuredClone(sample))
  for (const [key, value] of Object.entries(model)) data.replaceAll(data[key === 'span' ? 'timeline' : key], value)
  rebuild()
  vi.spyOn(api, 'capabilities').mockResolvedValue([])
  await router.push(path)
  const view = await appRouter.getRoutes().find((r) => r.name === name).components.default()
  wrapper = shallowMount(view.default, { global: { plugins: [router] } })
  await flushPromises()
  expect(wrapper.get('.page-head .page-title').text()).toBe(title)
  expect(wrapper.find('.page-head .eyebrow').exists()).toBe(false)
})
