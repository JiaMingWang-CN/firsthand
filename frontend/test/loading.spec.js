// 运行加载的并发与措辞：快速切换运行不能把上一个运行的数据当成当前运行；问题卡片不暗示报告没证明的因果。
// HTTP 层换成可控的桩（按运行 id 分别放行），数据取自 fixtures/sample.json。
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import sample from './fixtures/sample.json'

const gates = vi.hoisted(() => ({}))
const state = vi.hoisted(() => ({ abandon: false }))

vi.mock('../src/api/client.js', async (importOriginal) => {
  const { ApiError } = await importOriginal()
  const model = (id) => {
    const copy = structuredClone(sample)
    copy.overview.id = id
    copy.overview.product.metadata.name = `产品 ${id}`
    if (state.abandon) copy.experiences.p03.outcome = 'abandoned'
    // fixture 只保留了 3 名人物，而报告来自 10 人运行：把报告收窄到这 3 人，保持数据自洽
    const kept = new Set(copy.personas.map((p) => p.persona_id))
    const r = copy.report.report
    for (const key of ['issues', 'highlights']) {
      r.sections[key] = r.sections[key].map((item) => ({ ...item, affected_personas: item.affected_personas.filter((pid) => kept.has(pid)),
        evidence: item.evidence.filter((e) => kept.has(e.persona_id)) })).filter((item) => item.evidence.length)
    }
    r.silence_signals = r.silence_signals.filter((s) => kept.has(s.persona_id))
    r.consistency = r.consistency.filter((c) => kept.has(c.persona_id))
    const posts = new Set(copy.community.posts.map((x) => x.post_id))
    copy.community.reads = copy.community.reads.filter((x) => posts.has(x.post_id))
    return copy
  }
  // 每个运行 id 一道闸：overview 在闸打开前不返回，用来控制两次加载谁先完成
  const wait = async (id) => { await gates[id]?.promise }
  return {
    ApiError,
    api: {
      runs: async () => [],
      overview: async (id) => { await wait(id); return model(id).overview },
      personas: async (id) => model(id).personas,
      community: async (id) => model(id).community,
      report: async (id) => model(id).report,
      experience: async (id, pid) => model(id).experiences[pid],
    },
  }
})

const { ensureRun } = await import('../src/lib/live.js')
const data = await import('../src/lib/data.js')
const store = await import('../src/lib/store.js')

function gate(id) {
  let open, fail
  const promise = new Promise((resolve, reject) => { open = resolve; fail = reject })
  gates[id] = { promise, open, fail }
  return gates[id]
}
const settle = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); await new Promise((r) => setTimeout(r, 0)) }

beforeEach(() => {
  for (const key of Object.keys(gates)) delete gates[key]
  data.live.id = null
  data.live.status = 'idle'
  data.live.error = null
  state.abandon = false
})

describe('快速切换运行', () => {
  test('先发起的运行后返回时，不覆盖当前运行的数据，也不让闸门误判为就绪', async () => {
    const a = gate('run-a'), b = gate('run-b')
    const first = ensureRun('run-a')
    const second = ensureRun('run-b')
    a.open()
    await settle()
    // A 返回了，但当前运行是 B：既不能把 A 的数据当成 B 显示，也不能置为就绪
    expect(data.live.id).toBe('run-b')
    expect(data.live.status).toBe('loading')
    expect(data.product.name).not.toBe('产品 run-a')
    b.open()
    await Promise.all([first, second])
    expect(data.live.id).toBe('run-b')
    expect(data.live.status).toBe('ready')
    expect(data.product.name).toBe('产品 run-b')
    expect(data.run.id).toBe('run-b')
  })

  test('当前运行先完成、旧运行后完成时，旧运行的数据不会留在当前运行里', async () => {
    const a = gate('run-a'), b = gate('run-b')
    const first = ensureRun('run-a')
    const second = ensureRun('run-b')
    b.open()
    await second
    expect(data.product.name).toBe('产品 run-b')
    a.open()
    await first
    expect(data.live.id).toBe('run-b')
    expect(data.live.status).toBe('ready')
    expect(data.product.name).toBe('产品 run-b')
    expect(data.run.id).toBe('run-b')
  })

  test('旧运行加载失败不会把当前运行标成失败', async () => {
    const a = gate('run-a'), b = gate('run-b')
    const first = ensureRun('run-a')
    const second = ensureRun('run-b')
    a.fail(new Error('旧运行的错误'))
    await first
    expect(data.live.error).toBeNull()
    expect(data.live.status).toBe('loading')
    b.open()
    await second
    expect(data.live.status).toBe('ready')
    expect(data.product.name).toBe('产品 run-b')
  })

  test('切回仍在加载的运行时，最终显示的是它自己的数据', async () => {
    const a = gate('run-a'), b = gate('run-b')
    ensureRun('run-a')
    ensureRun('run-b')
    const again = ensureRun('run-a')
    a.open(); b.open()
    await again
    await settle()
    expect(data.live.id).toBe('run-a')
    expect(data.live.status).toBe('ready')
    expect(data.product.name).toBe('产品 run-a')
  })
})

test('大规模社区记录不会超过函数参数数量限制', async () => {
  const list = Array.from({ length: 150000 }, (_, i) => ({ pid: 'p01', t: i, post: 'post-1' }))
  const target = []
  data.replaceAll(target, list)
  expect(target.length).toBe(list.length)
  data.replaceAll(data.reads, list)
  const { rebuild, socialEvents } = await import('../src/lib/sim.js')
  rebuild()
  expect(socialEvents.filter((e) => e.kind === 'read').length).toBe(list.length)
  data.replaceAll(data.reads, [])
}, 15000)

test('切换运行时关闭上一个运行遗留的抽屉，免得它指向新运行里不存在的人物', async () => {
  await ensureRun('run-a')
  store.openDrawer({ type: 'persona', pid: 'p01' })
  expect(store.drawers.stack.length).toBe(1)
  await ensureRun('run-b')
  expect(store.drawers.stack.length).toBe(0)
})

describe('问题卡片的措辞', () => {
  test('被影响的人里有人最终没完成时，只陈述事实，不说是这个问题导致的', async () => {
    state.abandon = true
    await ensureRun('run-x')
    const { default: FindingCard } = await import('../src/components/FindingCard.vue')
    const issue = data.findings.find((f) => f.kind === 'issue' && f.affected.includes('p03'))
    expect(issue, '样本里应有影响 p03 的问题').toBeTruthy()
    expect(issue.unfinished).toEqual(['p03'])
    expect('quit' in issue).toBe(false)
    const text = mount(FindingCard, { props: { f: issue } }).text()
    expect(text).toContain('未完成')
    expect(text).not.toMatch(/放弃|因此|导致/)
  })
})
