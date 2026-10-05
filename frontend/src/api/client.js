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
  interview: (id, pid, body) => post(`${run(id)}/personas/${enc(pid)}/interview`, body),

  // 新建运行：资料 → 分析与推荐 → 确认人数与天数、生成人物 → 运行前审核 → 模拟与报告（后端以子进程执行命令行同一套步骤）
  checkManual: (text) => post('/api/manuals/check', { text }),
  capabilities: () => request('/api/capabilities'),
  drafts: () => request('/api/drafts'),
  newDraft: (manual, capabilityRun) => post('/api/drafts', { manual, capability_run: capabilityRun || null }),
  draft: (id) => request(`/api/drafts/${enc(id)}`),
  generatePersonas: (id, personaCount, durationDays) => post(`/api/drafts/${enc(id)}/personas`, { persona_count: personaCount, duration_days: durationDays }),
  editDraft: (id, body) => post(`/api/drafts/${enc(id)}/edits`, body),
  decide: (id, body) => post(`/api/drafts/${enc(id)}/decision`, body),
  simulate: (id) => post(`/api/drafts/${enc(id)}/simulations`, { confirm: true }),
  jobs: () => request('/api/jobs'),
  job: (id) => request(`/api/jobs/${enc(id)}`),
  jobLive: (id, persona) => request(`/api/jobs/${enc(id)}/live${persona ? `?persona=${enc(persona)}` : ''}`),
  jobShot: (id, pid, name) => `/api/jobs/${enc(id)}/shots/${enc(pid)}/${enc(name)}`,
}

function post(path, body) {
  return request(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
}
