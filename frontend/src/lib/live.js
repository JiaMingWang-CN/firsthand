// 从后端加载一次运行，转成 UI 数据并原地填入 data.js 的容器。
import { reactive } from 'vue'
import { api, ApiError } from '../api/client.js'
import { adapt } from '../api/adapt.js'
import * as data from './data.js'
import { rebuild } from './sim.js'
import { clock, pause } from './store.js'

export const runList = reactive({ status: 'idle', items: [], error: null })

export async function loadRunList() {
  runList.status = 'loading'
  try {
    runList.items = await api.runs()
    runList.status = 'ready'
    runList.error = null
  } catch (e) {
    runList.status = 'error'
    runList.error = e.message
  }
}

const noReport = (e) => e instanceof ApiError && e.status === 404

async function fetchRun(id) {
  const [overview, personas, community, report] = await Promise.all([
    api.overview(id), api.personas(id), api.community(id), api.report(id).catch((e) => { if (noReport(e)) return null; throw e }),
  ])
  const experiences = Object.fromEntries(await Promise.all(
    personas.filter((p) => p.experience).map(async (p) => [p.persona_id, await api.experience(id, p.persona_id)])))
  return { overview, personas, experiences, community, report }
}

let pending = null

/** 保证 data.js 里是 id 对应的运行；同一运行不重复加载 */
export async function ensureRun(id) {
  if (data.live.id === id && data.live.status === 'ready') return
  if (pending?.id === id) return pending.promise
  data.live.id = id
  data.live.status = 'loading'
  data.live.error = null
  const promise = (async () => {
    try {
      const model = adapt(await fetchRun(id))
      data.replaceAll(data.product, model.product)
      data.replaceAll(data.flows, model.flows)
      data.replaceAll(data.personas, model.personas)
      data.replaceAll(data.steps, model.steps)
      data.replaceAll(data.findings, model.findings)
      data.replaceAll(data.posts, model.posts)
      data.replaceAll(data.reads, model.reads)
      data.replaceAll(data.withheld, model.withheld)
      data.replaceAll(data.surveys, model.surveys)
      data.replaceAll(data.inconsistencies, model.inconsistencies)
      data.replaceAll(data.scout, model.scout)
      data.replaceAll(data.run, model.run)
      data.replaceAll(data.timeline, model.span)
      rebuild()
      pause()
      clock.t = model.span.total
      clock.stopped = false
      data.live.status = 'ready'
    } catch (e) {
      data.live.status = 'error'
      data.live.error = e.message
    } finally {
      pending = null
    }
  })()
  pending = { id, promise }
  return promise
}
