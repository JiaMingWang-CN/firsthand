// 状态栏提示与运行详情共用同一份用量明细。
import { computed } from 'vue'
import { run } from './data.js'

export const num = (n) => (n ?? 0).toLocaleString('zh-CN')
const tokens = (m) => `输入 ${num(m.input_tokens)}（缓存 ${num(m.cached_input_tokens)}）· 输出 ${num(m.output_tokens)}`
export const usageTip = computed(() => {
  const total = run.usage?.total ?? {}
  const models = run.usage?.models ?? []
  const model = models.length === 1 ? `（${models[0].model}）` : ''
  const lines = [`全程 ${num(total.requests)} 次请求${model}：${tokens(total)}`]
  if (models.length > 1) lines.push(...models.map((m) => `${m.model}：${tokens(m)}`))
  const iv = run.interviewUsage?.total
  if (iv?.requests) lines.push(`采访另计 ${num(iv.requests)} 次请求：${tokens(iv)}`)
  return lines.join(String.fromCharCode(10))
})
