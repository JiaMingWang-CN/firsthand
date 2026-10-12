// 运行前审核的侦察结果面板：默认只列有出入的说法，截图可打开，一致的可展开。
import { test, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ScoutPanel from '../src/components/ScoutPanel.vue'

const row = (id, verdict, extra = {}) => ({ claim_id: id, source: '说明书', area: id, says: '首页有注册按钮', verdict,
  observed: '看到的情况', observed_quote: '', screenshots: [], ...extra })

test('侦察完成：默认只列不一致与未核对，可展开一致的', async () => {
  const scout = { status: 'completed', reason: '', counts: { consistent: 1, inconsistent: 1, unverified: 1 }, checks: [
    row('flow:1:entry', 'consistent'),
    row('flow:1:steps', 'inconsistent', { observed_quote: '立即注册', screenshots: ['/api/drafts/d/scout/s001_after.png'] }),
    row('feature:1', 'unverified', { observed: '需登录' }),
  ] }
  const w = mount(ScoutPanel, { props: { scout } })
  expect(w.text()).toContain('不一致 1')
  expect(w.findAll('tbody tr')).toHaveLength(2)
  expect(w.find('a').attributes('href')).toBe('/api/drafts/d/scout/s001_after.png')
  expect(w.text()).toContain('页面原文：“立即注册”')
  await w.find('button').trigger('click')
  expect(w.findAll('tbody tr')).toHaveLength(3)
})

test('侦察未执行或失败时说明原因，尚未执行时不显示', () => {
  expect(mount(ScoutPanel, { props: { scout: { status: 'skipped', reason: '按要求跳过侦察', checks: [] } } }).text()).toContain('按要求跳过侦察')
  const failed = mount(ScoutPanel, { props: { scout: { status: 'failed', reason: 'TimeoutError', counts: { consistent: 0, inconsistent: 0, unverified: 1 },
    checks: [row('feature:1', 'unverified')] } } })
  expect(failed.text()).toContain('侦察没有完成（TimeoutError）')
  expect(mount(ScoutPanel, { props: { scout: { status: 'pending', checks: [] } } }).html()).not.toContain('侦察结果')
  expect(mount(ScoutPanel, { props: { scout: null } }).html()).not.toContain('侦察结果')
})
