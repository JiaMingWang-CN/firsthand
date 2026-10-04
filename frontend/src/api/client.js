// 后端接口的薄封装：只做请求和错误整理，不改数据形状（形状转换在 adapt.js）。

export class ApiError extends Error {
  /** reason：后端给出的机器可读原因（如采访的 invalid_answer / provider），可能没有 */
  constructor(status, detail, reason = null) {
    super(detail)
    this.status = status
    this.reason = reason
  }
}

async function request(path, options) {
  let res
  try {
    res = await fetch(path, options)
  } catch (e) {
    throw new ApiError(0, '无法连接后端接口，请确认 API 服务已启动（python -m api）')
  }
  if (!res.ok) {
    let detail = res.statusText, reason = null
    try {
      const body = await res.json()
      detail = body.detail ?? detail
      reason = body.reason ?? null
    } catch (e) { /* 响应不是 JSON 时用状态文本 */ }
    throw new ApiError(res.status, typeof detail === 'string' ? detail : JSON.stringify(detail), reason)
  }
  return res.json()
}

const enc = encodeURIComponent
const run = (id) => `/api/runs/${enc(id)}`

export const api = {
  runs: () => request('/api/runs'),
  overview: (id) => request(run(id)),
  personas: (id) => request(`${run(id)}/personas`),
  experience: (id, pid) => request(`${run(id)}/personas/${enc(pid)}/experience`),
  community: (id) => request(`${run(id)}/community`),
  report: (id, reportId) => request(`${run(id)}/report${reportId ? `?report_id=${enc(reportId)}` : ''}`),
  evidence: (id, ref) => request(`${run(id)}/evidence/${enc(ref)}`),
  recording: (id, pid) => request(`${run(id)}/personas/${enc(pid)}/recording`),
  interview: (id, pid, body) => request(`${run(id)}/personas/${enc(pid)}/interview`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }),
}
