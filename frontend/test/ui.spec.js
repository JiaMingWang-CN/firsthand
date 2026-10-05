// 组件测试：走真实的加载路径（App 加载闸门 → ensureRun → adapt → 页面），只把 HTTP 层和 hls.js 换成桩。
// 数据取自 fixtures/sample.json（真实样本的 3 名人物 p01 / p03 / p05）。
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import sample from './fixtures/sample.json'

const RUN = 'phase4-sample'
const TRACE = [
  { event_id: 't00093', type: 'network', level: 'error', text: 'GET https://example.com/_nuxt/app.js 503', video_seconds: 20 },
  { event_id: 't00120', type: 'console', level: 'warn', text: 'slow chunk', video_seconds: 21 },
]

const calls = vi.hoisted(() => ({ recording: [], interview: [], hls: [] }))
const state = vi.hoisted(() => ({ overviewError: null, recording: null, interviewError: null }))

vi.mock('../src/api/client.js', async (importOriginal) => {
  const { ApiError } = await importOriginal()
  const data = () => {
    const copy = structuredClone(sample)
    copy.experiences.p03.steps[0].trace = TRACE
    // fixture 只保留了 3 名人物，而报告来自 10 人运行：把报告收窄到这 3 人，保持数据自洽
    const kept = new Set(copy.personas.map((p) => p.persona_id))
    const r = copy.report.report
    for (const key of ['issues', 'highlights']) {
      r.sections[key] = r.sections[key].map((item) => ({ ...item, affected_personas: item.affected_personas.filter((pid) => kept.has(pid)),
        evidence: item.evidence.filter((e) => kept.has(e.persona_id)) })).filter((item) => item.evidence.length)
    }
    r.silence_signals = r.silence_signals.filter((s) => kept.has(s.persona_id))
    r.consistency = r.consistency.filter((c) => kept.has(c.persona_id))
    const posts = new Set(copy.community.posts.map((p) => p.post_id))
    copy.community.reads = copy.community.reads.filter((x) => posts.has(x.post_id))
    return copy
  }
  return {
    ApiError,
    api: {
      runs: async () => [],
      overview: async () => {
        if (state.overviewError) throw state.overviewError
        const n = calls.interview.length
        const interview_usage = n ? { total: { requests: 2 * n, input_tokens: 1000 * n, cached_input_tokens: 0, output_tokens: 50 * n } } : null
        return { ...data().overview, id: RUN, interview_usage }
      },
      personas: async () => data().personas,
      community: async () => data().community,
      report: async () => data().report,
      experience: async (id, pid) => data().experiences[pid],
      evidence: async (id, ref) => ({ ref_id: ref, category: 'experience', persona_id: 'p03', data: { agent_observation: `观察 ${ref}` }, files: [] }),
      recording: async (id, pid) => {
        calls.recording.push(pid)
        if (state.recording instanceof Error) throw state.recording
        return state.recording
      },
      interview: async (id, pid, body) => {
        calls.interview.push({ pid, body })
        if (state.interviewError) throw state.interviewError
        return { persona_id: pid, stance: 'answered', answer: '第三步我一直找不到按钮。', evidence: ['p03:step:3'] }
      },
    },
  }
})

vi.mock('hls.js', () => {
  class FakeHls {
    static isSupported() { return true }
    static Events = { MANIFEST_PARSED: 'manifestParsed', ERROR: 'error' }
    constructor() { this.handlers = {}; calls.hls.push(this) }
    on(name, fn) { this.handlers[name] = fn }
    loadSource(url) { this.url = url }
    attachMedia(video) { this.video = video; this.handlers.manifestParsed?.() }
    destroy() { this.destroyed = true }
  }
  return { default: FakeHls }
})

const { default: App } = await import('../src/App.vue')
const { router } = await import('../src/router.js')
const data = await import('../src/lib/data.js')
const store = await import('../src/lib/store.js')

const mounted = []
async function open(path) {
  await router.push(path)
  const wrapper = mount(App, { global: { plugins: [router] }, attachTo: document.body })
  mounted.push(wrapper)
  await router.isReady()
  for (let i = 0; i < 5; i++) await flushPromises()
  return wrapper
}

let errors
beforeEach(() => {
  errors = []
  vi.spyOn(console, 'error').mockImplementation((...a) => errors.push(a.join(' ')))
  vi.spyOn(console, 'warn').mockImplementation((...a) => errors.push(a.join(' ')))
  data.live.id = null
  data.live.status = 'idle'
  state.overviewError = null
  state.interviewError = null
  state.recording = { playlist_url: `/api/runs/${RUN}/personas/p03/recording.m3u8`, seek: { s005_before: 70, s005_after: 84 } }
  calls.recording.length = calls.interview.length = calls.hls.length = 0
  store.closeAllDrawers()
})
afterEach(() => {
  while (mounted.length) mounted.pop().unmount()
  vi.restoreAllMocks()
})

describe('每个带 runId 的页面都能用真实样本渲染', () => {
  for (const page of ['report', 'live', 'personas', 'community', 'interview']) {
    test(page, async () => {
      const w = await open(`/runs/${RUN}/${page}`)
      expect(w.find('.gate').exists()).toBe(false)
      expect(w.find('.page').exists(), w.html().slice(0, 500) + errors.join(' | ')).toBe(true)
      expect(errors).toEqual([])
    })
  }
})

test('后端拒绝运行时显示原因，重试后恢复', async () => {
  const { ApiError } = await import('../src/api/client.js')
  state.overviewError = new ApiError(422, 'phase4-sample: Experience file/database mismatch: p03')
  const w = await open(`/runs/${RUN}/report`)
  expect(w.find('[role="alert"]').text()).toContain('Experience file/database mismatch')
  state.overviewError = null
  await w.find('[role="alert"] button').trigger('click')
  for (let i = 0; i < 5; i++) await flushPromises()
  expect(w.find('[role="alert"]').exists()).toBe(false)
})

// 录像信息按人物缓存在页面会话内，所以先测失败（不入缓存），再测成功
describe('从报告问题跳到录像片段', () => {
  async function openIssueVideo() {
    const w = await open(`/runs/${RUN}/report`)
    const issue = data.findings.find((f) => f.evidence.some((e) => e.pid === 'p03' && e.kind === 'video'))
    const ev = issue.evidence.find((e) => e.pid === 'p03' && e.kind === 'video')
    store.openDrawer({ type: 'evidence', ev })
    for (let i = 0; i < 5; i++) await flushPromises()
    return { w, ev }
  }

  test('录像不可用时说明原因并给出估算秒数', async () => {
    const { ApiError } = await import('../src/api/client.js')
    state.recording = new ApiError(503, 'STEEL_API_KEY is not configured on the API server')
    const { w, ev } = await openIssueVideo()
    const text = w.find('.rec').text()
    expect(text).toContain('STEEL_API_KEY is not configured')
    const estimate = sample.experiences.p03.snapshots.find((s) => s.evidence_id === ev.snapshot).video_seconds
    expect(text).toContain(`${String(Math.floor(estimate / 60)).padStart(2, '0')}:${String(Math.round(estimate % 60)).padStart(2, '0')}`)
  })

  test('播放器定位到所引截图的录像时刻（前 5 秒起播），而不是该步骤操作前的截图', async () => {
    const { w, ev } = await openIssueVideo()
    expect(ev.snapshot).toBe('s005_after')
    expect(calls.recording).toEqual(['p03'])
    const hls = calls.hls.at(-1)
    expect(hls.url).toBe(`/api/runs/${RUN}/personas/p03/recording.m3u8`)
    expect(hls.video.currentTime).toBe(84 - 5)
    expect(w.find('.rec').text()).toContain('01:24')
  })
})

test('证据视图列出该步骤的 Console / Network 摘要', async () => {
  const w = await open(`/runs/${RUN}/report`)
  store.openDrawer({ type: 'evidence', ev: { pid: 'p03', step: 1, kind: 'network' } })
  await flushPromises()
  const lines = w.findAll('.trace .tl').map((l) => l.text())
  expect(lines).toHaveLength(2)
  expect(lines[0]).toContain('GET https://example.com/_nuxt/app.js 503')
  expect(lines[1]).toContain('slow chunk')
  store.openDrawer({ type: 'evidence', ev: { pid: 'p03', step: 2, kind: 'step' } })
  await flushPromises()
  expect(w.find('.trace').exists()).toBe(false)
})

test('时间轴缩放后，几分钟的体验条明显变宽并显示步骤刻度', async () => {
  const w = await open(`/runs/${RUN}/live`)
  const p03 = data.personas.find((p) => p.id === 'p03')
  store.seek(p03.slot + 2)
  await flushPromises()
  const lane = () => w.findAll('.rowlane')[data.personas.indexOf(p03)]
  const width = () => parseFloat(/width: ([\d.]+)%/.exec(lane().find('.browse').attributes('style'))[1])
  const day = width()
  expect(lane().findAll('.stepmark')).toHaveLength(0)
  await w.findAll('[aria-label="时间轴缩放"] button').find((b) => b.text() === '30 分钟').trigger('click')
  expect(width()).toBeGreaterThan(day * 40)
  expect(lane().findAll('.stepmark').length).toBeGreaterThan(0)
})

test('采访：带上已答的历史，展示回答与所引证据原文', async () => {
  const w = await open(`/runs/${RUN}/interview?pid=p03`)
  await w.find('input[aria-label="输入问题"]').setValue('哪一步最困惑？')
  await w.find('form').trigger('submit')
  for (let i = 0; i < 5; i++) await flushPromises()
  expect(calls.interview).toEqual([{ pid: 'p03', body: { question: '哪一步最困惑？', history: [] } }])
  expect(w.find('.msg.them .bubble').text()).toContain('第三步我一直找不到按钮。')
  expect(w.find('.iev').text()).toContain('观察 p03:step:3')
  await w.find('input[aria-label="输入问题"]').setValue('为什么？')
  await w.find('form').trigger('submit')
  for (let i = 0; i < 5; i++) await flushPromises()
  expect(calls.interview[1].body.history).toEqual([{ question: '哪一步最困惑？', answer: '第三步我一直找不到按钮。' }])
  // 采访的用量另记，答完后刷新累计
  expect(w.find('.usage').text()).toContain('累计 4 次模型请求')
  expect(w.find('.usage').text()).toContain('不计入运行本身的用量')
})

describe('采访失败时的提示与原因相符', () => {
  const cases = [
    [502, 'invalid_answer', '采访 p03 生成结果在 3 次尝试后仍不合法', '换个问法'],
    [502, 'provider', '模型服务出错：RateLimitError（HTTP 429）', '稍后再试'],
    [503, null, '模型服务出错：AuthenticationError（HTTP 401），请检查 config/.env 里的模型密钥与权限', '采访暂不可用'],
  ]
  for (const [status, reason, detail, hint] of cases) {
    test(`${status} ${reason ?? ''}`, async () => {
      const { ApiError } = await import('../src/api/client.js')
      state.interviewError = new ApiError(status, detail, reason)
      const w = await open(`/runs/${RUN}/interview?pid=p03`)
      await w.find('input[aria-label="输入问题"]').setValue('哪一步最困惑？')
      await w.find('form').trigger('submit')
      for (let i = 0; i < 5; i++) await flushPromises()
      const text = w.find('.msg.them .bubble').text()
      expect(text).toContain(hint)
      expect(text).toContain(detail)
      if (reason !== 'invalid_answer') expect(text).not.toContain('换个问法')
    })
  }
})
