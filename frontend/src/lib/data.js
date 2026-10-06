// 当前运行的数据。导出名与形状沿用早期演示数据，这样页面和组件不用改写；
// 容器是响应式的，加载新运行时原地替换内容（见 live.js）。
import { reactive } from 'vue'

export const product = reactive({ name: '' })
export const flows = reactive([])
export const personas = reactive([])
export const steps = reactive({})
export const findings = reactive([])
export const posts = reactive([])
export const reactions = reactive([]) // 后端有意不提供点赞，恒为空
export const reads = reactive([])
export const withheld = reactive([])
export const surveys = reactive({})
export const inconsistencies = reactive([])
export const scout = reactive([])
export const run = reactive({ id: null, usage: { models: [], total: {} } })
export const timeline = reactive({ total: 1440, sliceMinutes: 60, startMs: 0 })

export const live = reactive({ id: null, status: 'idle', error: null })

/** 原地替换，保持容器引用不变 */
export function replaceAll(target, value) {
  if (target === value) return
  if (Array.isArray(target)) {
    target.length = 0
    // Long timelines have hundreds of thousands of records; never spread them into one call.
    for (let offset = 0; offset < value.length; offset += 10000) target.push(...value.slice(offset, offset + 10000))
    return
  }
  for (const key of Object.keys(target)) delete target[key]
  Object.assign(target, value)
}
