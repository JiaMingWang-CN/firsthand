// 运行前审核的侦察结果面板：先显示计数，仅不一致默认展开；其余按需查看。
import { test, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ScoutPanel from '../src/components/ScoutPanel.vue'

const row = (id, verdict, extra = {}) => ({ claim_id: id, source: '说明书', area: id, says: '首页有注册按钮', verdict,
  observed: '看到的情况', observed_quote: '', screenshots: [], ...extra })

test('侦察完成：默认只列不一致，可查看全部核对结果', async () => {
  const scout = { status: 'completed', reason: '', counts: { consistent: 1, inconsistent: 1, unverified: 1 }, checks: [
    row('flow:1:entry', 'consistent'),
    row('flow:1:steps', 'inconsistent', { observed_quote: '立即注册', screenshots: ['/api/drafts/d/scout/s001_after.png'] }),
    row('feature:1', 'unverified', { observed: '需登录' }),
  ] }
  const w = mount(ScoutPanel, { props: { scout } })
  expect(w.text()).toContain('不一致 1')
  expect(w.find('.scout-summary').text()).toBe('一致 1 · 不一致 1 · 未核对 1')
  expect(w.findAll('tbody tr')).toHaveLength(1)
  expect(w.find('button').text()).toBe('查看全部 3 条')
  expect(w.find('a').attributes('href')).toBe('/api/drafts/d/scout/s001_after.png')
  expect(w.text()).toContain('页面原文：“立即注册”')
  await w.find('button').trigger('click')
  expect(w.findAll('tbody tr')).toHaveLength(3)
  expect(w.text()).toContain('需登录')
  await w.find('button').trigger('click')
  expect(w.findAll('tbody tr')).toHaveLength(1)
})

test('侦察未执行或失败时说明原因，尚未执行时不显示', () => {
  expect(mount(ScoutPanel, { props: { scout: { status: 'skipped', reason: '按要求跳过侦察', checks: [] } } }).text()).toContain('按要求跳过侦察')
  const failed = mount(ScoutPanel, { props: { scout: { status: 'failed', reason: 'TimeoutError', counts: { consistent: 0, inconsistent: 0, unverified: 1 },
    checks: [row('feature:1', 'unverified')] } } })
  expect(failed.text()).toContain('侦察没有完成（TimeoutError）')
  expect(mount(ScoutPanel, { props: { scout: { status: 'pending', checks: [] } } }).html()).not.toContain('侦察结果')
  expect(mount(ScoutPanel, { props: { scout: null } }).html()).not.toContain('侦察结果')
})

test('侦察失败的多项未核对默认收起，共同原因在展开前后都只出现一次', async () => {
  const reason = '浏览会话超时，侦察未完成，无法核对页面上的说法。'
  const scout = { status: 'failed', reason: 'TimeoutError', counts: { consistent: 0, inconsistent: 0, unverified: 14 },
    checks: Array.from({ length: 14 }, (_, i) => row('feature:' + i, 'unverified', { observed: reason })) }
  const w = mount(ScoutPanel, { props: { scout } })
  expect(w.find('.scout-summary').text()).toBe('一致 0 · 不一致 0 · 未核对 14')
  expect(w.find('table').exists()).toBe(false)
  expect(w.text().split(reason)).toHaveLength(2)
  expect(w.find('button').text()).toBe('查看全部 14 条')
  await w.find('button').trigger('click')
  expect(w.findAll('tbody tr')).toHaveLength(14)
  expect(w.text().split(reason)).toHaveLength(2)
  expect(w.find('tbody').text()).not.toContain(reason)
  await w.find('button').trigger('click')
  expect(w.find('table').exists()).toBe(false)
})

test('没有不一致时只显示摘要和查看全部入口，不把未核对误写成全部一致', async () => {
  const scout = { status: 'completed', counts: { consistent: 1, inconsistent: 0, unverified: 1 }, checks: [
    row('一', 'consistent', { observed: '入口可见' }), row('二', 'unverified', { observed: '需要登录' }),
  ] }
  const w = mount(ScoutPanel, { props: { scout } })
  expect(w.find('table').exists()).toBe(false)
  expect(w.find('.scout-summary').text()).toBe('一致 1 · 不一致 0 · 未核对 1')
  expect(w.text()).not.toContain('都与网站一致')
  await w.find('button').trigger('click')
  expect(w.findAll('tbody tr')).toHaveLength(2)
  expect(w.text()).toContain('入口可见')
  expect(w.text()).toContain('需要登录')
})

test('共享原因合并后，仍保留逐行的页面原文与截图', async () => {
  const scout = { status: 'completed', counts: { consistent: 0, inconsistent: 2, unverified: 0 }, checks: [
    row('一', 'inconsistent', { observed_quote: '原文一', screenshots: ['/shot.png'] }),
    row('二', 'inconsistent', { observed_quote: '原文二' }),
  ] }
  const w = mount(ScoutPanel, { props: { scout } })
  expect(w.text().split('看到的情况')).toHaveLength(2)
  expect(w.find('tbody').text()).not.toContain('看到的情况')
  expect(w.text()).toContain('页面原文：“原文一”')
  expect(w.text()).toContain('页面原文：“原文二”')
  expect(w.find('a').attributes('href')).toBe('/shot.png')
})
