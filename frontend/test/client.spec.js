// 接口封装：错误响应里的 detail 与 reason 原样带到 ApiError 上，非 JSON 响应退回状态文本。
import { test, expect, vi, afterEach } from 'vitest'
import { api, ApiError } from '../src/api/client.js'

const respond = (status, body, statusText = 'Bad Gateway') => vi.stubGlobal('fetch', vi.fn(async () =>
  new Response(typeof body === 'string' ? body : JSON.stringify(body), { status, statusText })))
afterEach(() => vi.unstubAllGlobals())

async function failure(call) {
  try { await call() } catch (e) { return e }
  throw new Error('应当失败')
}

test('错误带上后端给出的原因', async () => {
  respond(502, { detail: '模型服务出错：RateLimitError（HTTP 429）', reason: 'provider' })
  const e = await failure(() => api.interview('r', 'p03', { question: 'q', history: [] }))
  expect(e).toBeInstanceOf(ApiError)
  expect([e.status, e.message, e.reason]).toEqual([502, '模型服务出错：RateLimitError（HTTP 429）', 'provider'])
})

test('没有原因时为 null；detail 为空或响应不是 JSON 时用状态文本', async () => {
  respond(404, { detail: 'Unknown run: r' })
  expect((await failure(() => api.overview('r'))).reason).toBeNull()
  respond(500, { detail: null }, 'Internal Server Error')
  expect((await failure(() => api.overview('r'))).message).toBe('Internal Server Error')
  respond(500, '<html>oops</html>', 'Internal Server Error')
  const e = await failure(() => api.overview('r'))
  expect([e.message, e.reason]).toEqual(['Internal Server Error', null])
})

test('422 的结构化 detail 转成文字', async () => {
  respond(422, { detail: [{ loc: ['body', 'question'], msg: 'too long' }] }, 'Unprocessable Entity')
  expect((await failure(() => api.overview('r'))).message).toContain('too long')
})
