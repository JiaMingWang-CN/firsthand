<script setup>
// 任务进度：后端按步骤执行命令行的同一套模块，进度来自运行目录里已经写出的文件（timeline.json、各阶段结果）。
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api/client.js'
import FlowSteps from '../components/FlowSteps.vue'
import { AlertTriangle, Check, Loader, X, Circle, ExternalLink, Eye } from 'lucide-vue-next'

const route = useRoute()
const jobId = computed(() => String(route.params.jobId))
const state = ref({ status: 'loading', job: null, error: '' })
let timer = 0

// 现场：运行中的人物在做什么。pick 为空时跟随后端选的“正在浏览的人物”；点选某一步可固定查看那一步的截图
const live = ref({ personas: [], selected: null })
const pick = ref('')
const stepPick = ref(null)
async function loadLive() {
  try {
    live.value = await api.jobLive(jobId.value, pick.value)
  } catch (e) {
    if (pick.value) { pick.value = ''; live.value = await api.jobLive(jobId.value).catch(() => live.value) }  // 选中的人物不在了
  }
}

async function load() {
  clearTimeout(timer)
  try {
    const job = await api.job(jobId.value)
    state.value = { status: 'ready', job, error: '' }
    if (job.kind === 'simulate') await loadLive()
    if (job.state === 'running') timer = setTimeout(load, 2000)
  } catch (e) {
    state.value = { status: 'error', job: null, error: e.message }
  }
}
watch(jobId, () => { pick.value = ''; stepPick.value = null; live.value = { personas: [], selected: null }; load() }, { immediate: true })
function choose(pid) { pick.value = pid; stepPick.value = null; loadLive() }
const watching = computed(() => live.value.selected)
const steps = computed(() => (watching.value ? [...watching.value.steps].reverse() : []))
const shownStep = computed(() => {
  const all = watching.value?.steps ?? []
  return all.find((s) => s.n === stepPick.value) ?? [...all].reverse().find((s) => s.screenshot) ?? null
})
const shotUrl = computed(() => (shownStep.value?.screenshot ? api.jobShot(jobId.value, watching.value.id, shownStep.value.screenshot) : ''))
const PSTATE = { running: ['confused', '浏览中'], completed: ['pos', '已完成'], failed: ['neg', '失败'], cancelled: ['neg', '已取消'], pending: ['', '排队'] }
const hhmm = (iso) => (iso ? iso.slice(11, 16) : '')
onBeforeUnmount(() => clearTimeout(timer))

const job = computed(() => state.value.job)
const p = computed(() => job.value?.progress ?? {})
const STATE = { running: ['confused', '进行中'], succeeded: ['pos', '已完成'], failed: ['neg', '失败'],
  detached: ['confused', '无法跟踪'] }
const stepIcon = { pending: Circle, running: Loader, succeeded: Check, failed: X }
const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0)
const when = (iso) => (iso ? new Date(iso).toLocaleString('zh-CN', { hour12: false }) : '—')

// 流程条：这个任务在整个运行流程里是哪一步，结束后下一步去哪里（next 决定右侧按钮）
const flow = computed(() => {
  const j = job.value
  if (!j) return null
  const ended = { running: false, detached: false }[j.state] ?? true
  const ok = j.state === 'succeeded'
  if (j.kind === 'prepare') {
    if (!ended) return { at: 1, state: 'running', say: '正在探测模型能力、读取首页、生成产品模型并推荐人数与天数。完成后到审核页确认人数与天数。' }
    return ok ? { at: 2, state: 'active', next: 'review', label: '去确认人数与天数', say: '资料已分析完。下一步：确认或修改主 Agent 推荐的人数与天数，然后生成人物。' }
      : { at: 1, state: 'failed', next: 'new', say: '资料分析没有完成，原因见下方日志。修正后需要新建一次运行。' }
  }
  if (j.kind === 'generate') {
    if (!ended) return { at: 3, state: 'running', say: '正在规划人群分布并逐个补全人物，人多时需要较长时间。完成后到审核页核对并批准。' }
    return ok ? { at: 4, state: 'active', next: 'review', label: '去审核', say: '人物已生成。下一步：核对人物与运行配置，没问题就批准。' }
      : { at: 3, state: 'failed', next: 'review', label: '回到草稿重试', say: '生成人物没有完成，原因见下方日志。可以回到草稿直接重试，或换个人数。' }
  }
  const at = p.value.phase4_passed != null ? 6 : 5
  if (!ended) return { at, state: 'running', say: at === 6 ? '体验与讨论已结束，正在生成报告。' : '人物正在按作息体验产品、在社区讨论。完成后自动生成报告。' }
  return ok ? { at: 6, state: 'done', next: 'report', say: '体验、讨论与报告都已完成，可以查看报告、回放和采访人物。' }
    : { at, state: 'failed', next: 'review', label: '回到草稿重新模拟', say: `${at === 6 ? '生成报告' : '模拟'}没有完成，原因见下方日志。修正后可以回到草稿重新开始模拟。` }
})
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <div class="eyebrow">任务 · <span class="num">{{ jobId }}</span></div>
        <h1 class="page-title">{{ { simulate: '模拟与报告', prepare: '分析资料' }[job?.kind] ?? '生成人物草稿' }}</h1>
        <p class="page-sub">任务在后端以子进程执行与命令行相同的步骤；页面每 2 秒读取一次运行目录里的进度。关闭页面不会中断任务。</p>
      </div>
      <span v-if="job" class="tag" :class="STATE[job.state]?.[0]"><span class="dot"></span>{{ STATE[job.state]?.[1] ?? job.state }}</span>
    </header>

    <div v-if="state.status === 'loading'" class="panel"><p class="faint">正在读取任务…</p></div>
    <div v-else-if="state.status === 'error'" class="panel" role="alert"><p>{{ state.error }}</p></div>
    <template v-else>
      <FlowSteps :at="flow.at" :state="flow.state">
        {{ flow.say }}<template v-if="job.state === 'detached'">（协调进程已失联，见下方说明）</template>
        <template #action>
          <RouterLink v-if="flow.next === 'review'" class="btn btn-primary sm" :to="{ name: 'review', params: { draftId: job.draft } }">{{ flow.label }}</RouterLink>
          <RouterLink v-else-if="flow.next === 'new'" class="btn btn-secondary sm" to="/new">新建运行</RouterLink>
          <RouterLink v-else-if="flow.next === 'report'" class="btn btn-primary sm" :to="{ name: 'report', params: { runId: job.simulation } }">查看报告</RouterLink>
        </template>
      </FlowSteps>

      <div v-if="job.state === 'detached'" class="warn block"><AlertTriangle /><div>这个任务的协调进程已经失联，它的阶段进程可能仍在后台运行，所以它继续占用模拟或草稿的预留。下面的进度仍按运行目录里的文件显示。确认没有阶段进程在运行后，在 backend 目录执行 <code>python -m api.abandon_job {{ job.id }}</code> 释放占用（旧版本任务需加 <code>--force</code>）；不会自动重跑付费步骤。</div></div>

      <section class="panel">
        <ol class="steps">
          <li v-for="(s, i) in job.steps" :key="i" :class="s.state">
            <component :is="stepIcon[s.state]" :class="{ spin: s.state === 'running' }" /><span>{{ s.name }}</span>
          </li>
        </ol>

        <template v-if="job.kind === 'simulate'">
          <div class="meter">
            <div class="label">时间片 <span class="num">{{ p.slices_done }}/{{ p.slices }}</span></div>
            <div class="bar"><i :style="{ width: pct(p.slices_done, p.slices) + '%' }"></i></div>
          </div>
          <div class="meter">
            <div class="label">完成体验的人物 <span class="num">{{ p.personas_done }}/{{ p.personas }}</span><span v-if="p.personas_failed" class="neg"> · 失败 {{ p.personas_failed }}</span></div>
            <div class="bar"><i :style="{ width: pct(p.personas_done, p.personas) + '%' }"></i></div>
          </div>
          <p class="faint small">阶段 4 验收：{{ p.phase4_passed == null ? '尚未完成' : p.phase4_passed ? '通过' : '未通过' }} · 报告：{{ p.report_passed == null ? '尚未生成' : p.report_passed ? '已生成' : '未通过校验' }}</p>
          <div class="row links">
            <RouterLink v-if="p.phase4_passed != null" class="btn btn-secondary sm" :to="{ name: 'report', params: { runId: job.simulation } }">打开这次运行</RouterLink>
            <RouterLink class="btn btn-ghost sm" :to="{ name: 'review', params: { draftId: job.draft } }">查看人物草稿</RouterLink>
          </div>
        </template>
        <template v-else>
          <ul class="checks">
            <template v-if="job.kind === 'prepare'">
              <li :class="{ ok: p.capability }"><Check v-if="p.capability" /><Circle v-else />能力文件</li>
              <li :class="{ ok: p.site }"><Check v-if="p.site" /><Circle v-else />首页摘录</li>
              <li :class="{ ok: p.product }"><Check v-if="p.product" /><Circle v-else />产品模型与人数、天数推荐</li>
            </template>
            <li v-else :class="{ ok: p.draft }"><Check v-if="p.draft" /><Circle v-else />人物草稿</li>
          </ul>
          <div class="row links">
            <RouterLink class="btn btn-secondary sm" :to="{ name: 'review', params: { draftId: job.draft } }">{{ job.state !== 'succeeded' ? '查看草稿' : job.kind === 'prepare' ? '去确认人数与天数' : '去审核' }}</RouterLink>
          </div>
        </template>
        <p class="faint small">开始于 {{ when(job.created_at) }}<template v-if="job.finished_at"> · 结束于 {{ when(job.finished_at) }}</template></p>
      </section>

      <section v-if="job.kind === 'simulate' && live.personas.length" class="panel watch">
        <div class="panel-head"><h3><Eye class="hi" />现场</h3><span class="aside faint">按各自的步骤日志与截图实时更新；浏览结束后的完整回放在“打开这次运行”里</span></div>
        <div class="who" role="tablist" aria-label="人物">
          <button v-for="p in live.personas" :key="p.id" type="button" role="tab" class="pill" :class="{ on: watching?.id === p.id }" :aria-selected="watching?.id === p.id" @click="choose(p.id)">
            <span class="dot" :class="PSTATE[p.state]?.[0]"></span><b class="num">{{ p.id }}</b><span>{{ p.name }}</span>
          </button>
        </div>
        <template v-if="watching">
          <div class="who-head">
            <div><b>{{ watching.name }}</b><span class="faint"> · {{ watching.profession }} · {{ watching.age }} 岁 · {{ watching.city }}<template v-if="watching.local_time"> · 本地 {{ hhmm(watching.local_time) }}</template></span></div>
            <span class="tag" :class="PSTATE[watching.state]?.[0]"><span class="dot"></span>{{ PSTATE[watching.state]?.[1] ?? watching.state }}</span>
            <a v-if="watching.viewer_url" class="btn btn-secondary sm" :href="watching.viewer_url" target="_blank" rel="noopener noreferrer"><ExternalLink />在 Steel 中实时观看</a>
          </div>
          <div class="stage">
            <figure class="shot">
              <img v-if="shotUrl" :src="shotUrl" :alt="`${watching.name} 第 ${shownStep.n} 步之后的页面`" />
              <div v-else class="faint noshot"><Loader v-if="watching.state === 'running'" class="spin" />{{ watching.state === 'running' ? '浏览器刚打开，等第一步完成后出现截图…' : '这位人物没有截图' }}</div>
              <figcaption v-if="shownStep && shotUrl" class="faint">第 {{ shownStep.n }} 步操作后的页面</figcaption>
            </figure>
            <ol class="steplist" aria-label="步骤">
              <li v-if="!steps.length" class="faint">还没有开始第一步。</li>
              <li v-for="s in steps" :key="s.n" :class="{ on: shownStep?.n === s.n }">
                <button type="button" class="stepbtn" @click="stepPick = s.n">
                  <span class="sn num">{{ s.n }}</span>
                  <span class="sb">
                    <span v-if="s.eval" class="evl">{{ s.eval }}</span>
                    <span v-if="s.goal" class="goal">▸ {{ s.goal }}</span>
                    <code v-for="(a, i) in s.actions" :key="i" class="act">{{ a }}</code>
                    <span v-for="(r, i) in s.results" :key="'r' + i" class="faint res">{{ r }}</span>
                  </span>
                </button>
                <details v-if="s.memory" class="mem"><summary class="faint">记下的内容</summary><p>{{ s.memory }}</p></details>
              </li>
            </ol>
          </div>
        </template>
      </section>

      <section class="panel">
        <div class="panel-head"><h3>日志</h3><span class="aside faint">最近 {{ job.log.length }} 行 · 已去除密钥</span></div>
        <pre v-if="job.log.length" class="log">{{ job.log.join('\n') }}</pre>
        <p v-else class="faint">还没有输出。</p>
      </section>
    </template>
  </div>
</template>

<style scoped>
.block { margin-bottom: var(--sp-4); }
.steps { list-style: none; padding: 0; margin: 0 0 var(--sp-4); display: grid; gap: var(--sp-2); }
.steps li { display: flex; align-items: center; gap: var(--sp-2); font-size: var(--fs-sm); color: var(--text-3); }
.steps li.running { color: var(--text); font-weight: 600; }
.steps li.succeeded { color: var(--text-2); }
.steps li.failed { color: var(--neg); }
.steps svg, .checks svg { width: 16px; height: 16px; stroke-width: 1.5; }
.steps li.succeeded svg, .checks li.ok svg { color: var(--pos); }
.meter { margin-bottom: var(--sp-3); }
.meter .label { font-size: var(--fs-sm); margin-bottom: 4px; }
.bar { height: 6px; background: var(--surface-2); border-radius: 0; overflow: hidden; }
.bar i { display: block; height: 100%; background: var(--sim); transition: width var(--dur-slow) var(--ease); }
.neg { color: var(--neg); }
.checks { list-style: none; padding: 0; margin: 0 0 var(--sp-3); display: flex; gap: var(--sp-4); font-size: var(--fs-sm); }
.checks li { display: flex; align-items: center; gap: 6px; color: var(--text-3); }
.checks li.ok { color: var(--text); }
.links { gap: var(--sp-2); margin: var(--sp-3) 0; }
.small { font-size: var(--fs-xs); margin: var(--sp-2) 0 0; }
.log { background: var(--surface-2); border-radius: var(--r-md); padding: var(--sp-3); font-family: var(--font-mono); font-size: var(--fs-xs); max-height: 420px; overflow: auto; white-space: pre-wrap; margin: 0; }
.watch { margin-bottom: var(--sp-4); }
.hi { width: 16px; height: 16px; stroke-width: 1.5; vertical-align: -3px; margin-right: 6px; }
.who { display: flex; flex-wrap: wrap; gap: var(--sp-2); margin-bottom: var(--sp-3); }
.pill { display: inline-flex; align-items: center; gap: 6px; padding: 4px 12px; border: 1px solid var(--border); border-radius: 0; background: var(--surface); color: var(--text-2); font: inherit; font-size: var(--fs-sm); cursor: pointer; }
.pill.on { border-color: var(--text); color: var(--text); }
.pill .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text-3); }
.pill .dot.pos { background: var(--pos); }
.pill .dot.neg { background: var(--neg); }
.pill .dot.confused { background: var(--confused); }
.who-head { display: flex; align-items: center; gap: var(--sp-3); margin-bottom: var(--sp-3); font-size: var(--fs-sm); }
.who-head > div { margin-right: auto; }
.stage { display: grid; grid-template-columns: minmax(240px, 2fr) minmax(0, 3fr); gap: var(--sp-4); align-items: start; }
.shot { margin: 0; position: sticky; top: var(--sp-4); }
.shot img { width: 100%; border: 1px solid var(--border); border-radius: var(--r-md); display: block; background: var(--surface-2); }
.shot figcaption { font-size: var(--fs-xs); margin-top: 4px; }
.noshot { display: flex; align-items: center; justify-content: center; gap: var(--sp-2); min-height: 200px; border: 1px dashed var(--border-strong); border-radius: var(--r-md); text-align: center; padding: var(--sp-4); font-size: var(--fs-sm); }
.steplist { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--sp-2); max-height: 560px; overflow: auto; }
.steplist li { border: 1px solid var(--border); border-radius: var(--r-md); }
.steplist li.on { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-ring); }
.stepbtn { display: flex; gap: var(--sp-3); width: 100%; text-align: left; padding: var(--sp-2) var(--sp-3); background: none; border: none; font: inherit; color: inherit; cursor: pointer; }
.sn { flex: none; width: 22px; height: 22px; border-radius: 50%; background: var(--surface-2); display: grid; place-items: center; font-size: var(--fs-xs); }
.sb { display: grid; gap: 4px; min-width: 0; font-size: var(--fs-sm); overflow-wrap: anywhere; }
.evl { color: var(--text-2); }
.goal { font-weight: 600; }
.act { font-size: var(--fs-xs); background: var(--surface-2); padding: 2px 6px; border-radius: var(--r-sm); word-break: break-all; }
.res { font-size: var(--fs-xs); }
.mem { padding: 0 var(--sp-3) var(--sp-2) calc(var(--sp-3) * 2 + 22px); font-size: var(--fs-xs); }
.mem p { margin: 4px 0 0; color: var(--text-2); }
@media (max-width: 959px) { .stage { grid-template-columns: 1fr; } .shot { position: static; } }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
