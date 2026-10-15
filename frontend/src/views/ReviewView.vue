<script setup>
// 运行前审核：与命令行 orchestrator.phase1 review 同一套规则、读写同一份审批记录。
// 先确认（或修改）主 Agent 推荐的人数与天数，再生成人物；生成后可改天数和每个人的采样参数（改动后要重新批准）。
// 批准与修改都带上页面展示版本的哈希：展示后草稿被改过，后端会拒绝，要求重新加载再看一遍。
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/client.js'
import { label, TEXT_ONLY_NOTE } from '../lib/sim.js'
import { askConfirm, toast } from '../lib/store.js'
import FlowSteps from '../components/FlowSteps.vue'
import ScoutPanel from '../components/ScoutPanel.vue'
import { AlertTriangle, Check, RefreshCw, Play, Info, Loader, Users } from 'lucide-vue-next'
import PageIntro from '../components/PageIntro.vue'
import { useClamp } from '../lib/useClamp.js'

const route = useRoute()
const router = useRouter()
const draftId = computed(() => String(route.params.draftId))
const state = ref({ status: 'loading', data: null, error: '' })
const job = ref(null) // 生成这份草稿的任务（生成中或失败时显示日志）
const simJob = ref(null) // 批准后由这份草稿发起的最近一次模拟任务（流程条据此显示模拟与报告进度）
const actionsEl = ref(null)
const overrides = ref(false)
const busy = ref(false)
const actionError = ref('')
const open = ref(null)
const materialOpen = ref(false)
const featuresOpen = ref(false)
const rationaleEl = ref(null)
const { expanded: rationaleOpen, truncated: rationaleTruncated } = useClamp(() => [rationaleEl.value], () => d.value?.cohort_rationale)
let timer = 0

async function load() {
  clearTimeout(timer)
  try {
    const data = await api.draft(draftId.value)
    if (BUSY.includes(data.status) || ['failed', 'incomplete'].includes(data.status) || data.generation_error) {
      const jobs = await api.jobs()  // 最新的在前：重新生成时显示最近一次
      const mine = jobs.find((j) => ['prepare', 'generate'].includes(j.kind) && j.draft === draftId.value)
      job.value = mine ? await api.job(mine.id) : null
    } else {
      job.value = null
    }
    if (data.status === 'configuring' && !size.value.touched && data.recommendation) {
      size.value = { count: data.recommendation.persona_count, days: data.recommendation.duration_days, touched: false }
    }
    if (data.run_config) days.value = data.run_config.duration_days
    simJob.value = data.status === 'approved'
      ? ((await api.jobs().catch(() => [])) ?? []).find((j) => j.kind === 'simulate' && j.draft === draftId.value) ?? null
      : null
    state.value = { status: 'ready', data, error: '' }
    if (BUSY.includes(data.status) || simJob.value?.state === 'running') timer = setTimeout(load, 3000)
  } catch (e) {
    state.value = { status: 'error', data: null, error: e.message }
  }
}

const d = computed(() => state.value.data)
const people = computed(() => {
  const rows = Object.fromEntries((d.value?.schedule ?? []).map((r) => [r.persona_id, r]))
  return (d.value?.personas ?? []).map((p) => ({ ...p, row: rows[p.persona_id] ?? {} }))
})
const STATUS = {
  analyzing: ['confused', '分析中'], text_only: ['neg', '待确认：模型不支持识图'], configuring: ['confused', '待确认人数与天数'],
  generating: ['confused', '生成中'], failed: ['neg', '生成失败'], incomplete: ['neg', '生成未完成'],
  pending: ['', '待审核'], approved: ['pos', '已批准'], rejected: ['neg', '已拒绝'], stale: ['confused', '审批已失效'],
}
const status = computed(() => STATUS[d.value?.status] ?? ['', d.value?.status])
const BUSY = ['analyzing', 'generating']
const canDecide = computed(() => d.value?.valid && ['pending', 'stale', 'rejected'].includes(d.value.status))
// 顶部摘要和底部审核区共用同一组禁用条件与操作。
const approveDisabled = computed(() => busy.value || !!d.value?.blocked || (d.value?.issues.length > 0 && !overrides.value))
const rejectDisabled = computed(() => busy.value || d.value?.status === 'rejected')
const features = computed(() => d.value?.product?.features ?? [])
const LEVEL = { complete: ['pos', '资料完整'], partial: ['confused', '资料不全'], limited: ['neg', '参考性有限'] }

// 流程条：这份草稿走到了哪一步、已完成什么、接下来做什么（next 决定流程条右侧的按钮）
const flow = computed(() => {
  const v = d.value
  if (!v) return null
  switch (v.status) {
    case 'analyzing': return { at: 1, state: 'running', say: '正在探测模型能力、读取首页、生成产品模型并推荐人数与天数。完成后本页自动进入下一步。' }
    case 'text_only': return { at: 1, state: 'active', next: 'text_only', say: '探测发现当前模型不支持图像识别。确认接受“参考性有限”后才会继续分析；不接受可以换一个识图模型，新建运行。' }
    case 'failed': case 'incomplete': return { at: 1, state: 'failed', next: 'new', say: '资料分析没有完成，原因与日志见下方。修正后需要新建一次运行。' }
    case 'configuring': return { at: 2, state: 'active', say: v.generation_error ? '上次生成人物没有成功，可以在下方直接重试，或换个人数。' : '资料已分析完。下一步：在下方确认或修改人数与天数，然后点“生成人物”。' }
    case 'generating': return { at: 3, state: 'running', say: '正在规划人群分布并逐个补全人物，人多时需要较长时间。完成后本页自动进入审核。' }
  }
  if (!v.valid) return { at: 4, state: 'failed', say: '草稿未通过校验，不能批准。修改运行目录里的 draft.json 后点“重新加载”。' }
  if (v.status !== 'approved') {
    return { at: 4, state: 'active', next: 'approve', say: v.blocked ? '这份草稿现在不能批准，原因见下方。' : {
      pending: '人物已生成。下一步：核对下方的人物与运行配置，没问题就点“批准”。',
      stale: '批准后草稿被修改过，审批已失效。下一步：重新核对，再次批准。',
      rejected: '这份草稿已被拒绝。可以重新核对后批准，或新建一次运行。' }[v.status] }
  }
  const s = simJob.value
  const reporting = s?.progress?.phase4_passed != null
  if (s && ['running', 'detached'].includes(s.state)) {
    return { at: reporting ? 6 : 5, state: 'running', next: 'job', say: reporting ? '体验与讨论已结束，正在生成报告。'
      : `人物正在按作息体验产品、在社区讨论（完成体验 ${s.progress?.personas_done ?? 0}/${s.progress?.personas ?? '—'} 人）。完成后自动生成报告。` }
  }
  if (s?.state === 'failed') return { at: reporting ? 6 : 5, state: 'failed', next: 'job', say: '上次模拟没有完成。查看任务日志找原因，可以点“重新开始模拟”重试。' }
  const run = s?.simulation ?? v.simulations[0]
  if (run) return { at: 6, state: 'done', next: 'report', run, say: '体验、讨论与报告都已完成，可以查看报告、回放和采访人物。' }
  return { at: 5, state: 'active', next: 'simulate', say: '已批准。下一步：开始模拟——人物按作息用真实浏览器体验产品、在社区讨论，最后生成报告。' }
})
// 已批准后只在尚未模拟或上次失败时提供入口，顶部与底部共用。
const canSimulate = computed(() => d.value?.valid && d.value.status === 'approved' &&
  (flow.value?.next === 'simulate' || (flow.value?.next === 'job' && flow.value.state === 'failed')))
const summaryTitle = computed(() => canDecide.value ? '你要批准的是' : flow.value?.state === 'failed' ? '已批准 · 上次模拟没有完成' : '已批准')
const toActions = () => actionsEl.value?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })

// —— 人数与天数：主 Agent 推荐，用户可改；人物生成后人数固定（换人数需新建运行），天数仍可改 ——
const size = ref({ count: null, days: null, touched: false })
const limits = computed(() => d.value?.limits ?? { personas: [2, 99], days: [1, 365] })
const sizeError = computed(() => {
  const { count, days: n } = size.value
  const [lo, hi] = limits.value.personas
  if (!Number.isInteger(count) || count < lo || count > hi) return `人数须是 ${lo}–${hi} 的整数`
  if (d.value?.minimum_personas && count < d.value.minimum_personas) return `说明书里的关键流程至少需要 ${d.value.minimum_personas} 人`
  if (!Number.isInteger(n) || n < 1 || n > limits.value.days[1]) return `天数须是 1–${limits.value.days[1]} 的整数`
  return ''
})
async function generate() {
  const { count, days: n } = size.value
  const ok = await askConfirm({
    title: `生成 ${count} 名人物`,
    body: `将调用模型规划 ${count} 人的分布（每批 10 人），再逐个补全身份、背景、性格与作息，模拟时间线 ${n} 天。人数越多，生成和之后的模拟用量越大、耗时越长。生成后人数不能再改，天数可以在审核时调整。`,
    confirmText: '开始生成',
  })
  if (!ok) return
  busy.value = true
  actionError.value = ''
  try {
    await api.generatePersonas(draftId.value, count, n)
    await load()
  } catch (e) {
    actionError.value = e.message
  } finally {
    busy.value = false
  }
}

// —— 模型不支持识图：用户接受参考性有限后，才继续分析（不再重新探测）——
async function acceptTextOnly() {
  const ok = await askConfirm({
    title: '使用纯文本模型继续',
    body: `${TEXT_ONLY_NOTE}。确认后继续读取首页、生成产品模型和人数、天数推荐，会产生模型用量。`,
    confirmText: '接受并继续',
  })
  if (!ok) return
  busy.value = true
  actionError.value = ''
  try {
    await api.resumeAnalysis(draftId.value)
    await load()
  } catch (e) {
    actionError.value = e.message
  } finally {
    busy.value = false
  }
}

// —— 审核时的修改：天数、每个人的采样参数 ——
const days = ref(null)
const latestDay = computed(() => Math.max(1, ...(d.value?.personas ?? []).map((p) => p.schedule.browse_day ?? 1)))
const editing = ref({}) // persona_id -> { temperature, top_p, presence_penalty }
function editSampling(p) {
  editing.value = { ...editing.value, [p.persona_id]: { ...(p.sampling ?? { temperature: 0.7, top_p: 0.95, presence_penalty: 0 }) } }
}
async function saveEdit(body, what) {
  busy.value = true
  actionError.value = ''
  try {
    await api.editDraft(draftId.value, { draft_sha256: d.value.draft_sha256, ...body })
    toast(`已保存${what}${d.value.status === 'approved' ? '，需要重新批准' : ''}`)
    editing.value = {}
    await load()
  } catch (e) {
    actionError.value = e.message
  } finally {
    busy.value = false
  }
}
const samplingNote = computed(() => {
  const s = d.value?.sampling
  if (!s) return ''
  if (!s.probed) return '这份草稿用的能力文件没有探测采样参数：运行时不会发送人物各自的温度、top_p，所有人仍用框架默认值。新建运行时选“重新探测”可启用。'
  if (!s.chat) return '模型服务没有接受采样参数（能力探测未通过）：运行时不会发送，所有人仍用框架默认值。'
  if (s.thinking === 'enabled') return '当前开启了思考模式，部分模型在思考时会忽略温度、top_p，人物之间的差异主要来自人设。'
  return ''
})

async function decide(decision) {
  const approving = decision === 'approve'
  const ok = await askConfirm(approving
    ? { title: '批准这份草稿', body: '批准的是页面上展示的这一版人物与运行配置。批准后可以开始模拟；之后再修改说明书、草稿或能力文件，审批会失效。', confirmText: '批准' }
    : { title: '拒绝这份草稿', body: '拒绝后不能用这份草稿开始模拟。可以修改 draft.json 后重新加载再审核，或新建一次运行。', confirmText: '拒绝', danger: true })
  if (!ok) return
  busy.value = true
  actionError.value = ''
  try {
    await api.decide(draftId.value, { decision, draft_sha256: d.value.draft_sha256, accept_overrides: overrides.value })
    toast(approving ? '已批准' : '已拒绝')
    await load()
  } catch (e) {
    actionError.value = e.message
  } finally {
    busy.value = false
  }
}

async function simulate() {
  const ok = await askConfirm({
    title: '开始模拟',
    body: `将按批准的作息让 ${d.value.personas.length} 名人物用真实浏览器（Steel）体验产品，并在社区讨论、填写离场问卷，最后生成报告。会产生模型与 Steel 用量，通常需要数十分钟；同一时间只能运行一次模拟。`,
    confirmText: '开始模拟',
  })
  if (!ok) return
  busy.value = true
  actionError.value = ''
  try {
    const started = await api.simulate(draftId.value)
    router.push({ name: 'job', params: { jobId: started.id } })
  } catch (e) {
    actionError.value = e.message
  } finally {
    busy.value = false
  }
}
// 放在最后：immediate 会立即调用 load，它用到上面定义的状态
watch(draftId, () => {
  state.value = { status: 'loading', data: null, error: '' }
  overrides.value = false
  materialOpen.value = false
  featuresOpen.value = false
  rationaleOpen.value = false
  size.value = { count: null, days: null, touched: false }
  load()
}, { immediate: true })
onBeforeUnmount(() => clearTimeout(timer))
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <div class="eyebrow">运行前审核</div>
        <h1 class="page-title">{{ d?.manual?.name ?? d?.product ?? '运行前审核' }}</h1>
        <PageIntro>人物与运行配置在执行前需要人工确认。规则与命令行审核相同：批准的是页面展示的这一版；人群分布与规划不一致时，需要明确确认这些变更。</PageIntro>
      </div>
      <div class="row">
        <span v-if="d?.text_only" class="tag neg" :title="TEXT_ONLY_NOTE"><span class="dot"></span>参考性有限 · 纯文本模型</span>
        <span v-if="d" class="tag" :class="status[0]"><span class="dot"></span>{{ status[1] }}</span>
        <button class="btn btn-secondary" type="button" :disabled="busy" @click="load"><RefreshCw />重新加载</button>
      </div>
    </header>

    <FlowSteps v-if="flow" :at="flow.at" :state="flow.state">
      {{ flow.say }}
      <template #action>
        <RouterLink v-if="flow.next === 'new'" class="btn btn-secondary sm" to="/new">新建运行</RouterLink>
        <button v-else-if="flow.next === 'text_only'" class="btn btn-primary sm" type="button" :disabled="busy" @click="acceptTextOnly">接受并继续分析</button>
        <button v-else-if="flow.next === 'approve' && canDecide" class="btn btn-secondary sm" type="button" @click="toActions">前往审核区</button>
        <button v-else-if="flow.next === 'simulate'" class="btn btn-primary sm" type="button" :disabled="busy" @click="simulate"><Play />开始模拟</button>
        <RouterLink v-else-if="flow.next === 'job'" class="btn btn-secondary sm" :to="{ name: 'job', params: { jobId: simJob.id } }">{{ flow.state === 'failed' ? '查看任务日志' : '查看模拟进度' }}</RouterLink>
        <RouterLink v-else-if="flow.next === 'report'" class="btn btn-primary sm" :to="{ name: 'report', params: { runId: flow.run } }">查看报告</RouterLink>
      </template>
    </FlowSteps>

    <div v-if="state.status === 'loading'" class="panel"><p class="faint">正在读取草稿…</p></div>
    <div v-else-if="state.status === 'error'" class="panel" role="alert"><p>{{ state.error }}</p></div>

    <template v-else>
      <section v-if="canDecide || canSimulate" class="panel approval-summary block" :aria-label="summaryTitle">
        <div class="summary-copy">
          <b>{{ summaryTitle }}</b>
          <p>{{ d.manual.name }} · {{ d.personas.length }} 人 · {{ d.run_config.duration_days }} 天 · {{ d.capability.model }} · {{ d.issues.length ? '需确认 ' + d.issues.length + ' 项分布变更' : '无需额外确认' }}</p>
          <button v-if="canDecide && d.issues.length" class="btn btn-ghost sm" type="button" @click="toActions">前往勾选分布变更</button>
          <p v-if="actionError" class="neg" role="alert">{{ actionError }}</p>
        </div>
        <div class="row summary-buttons">
          <template v-if="canDecide">
            <button class="btn btn-danger" type="button" :disabled="rejectDisabled" @click="decide('reject')">拒绝</button>
            <button class="btn btn-primary" type="button" :disabled="approveDisabled" @click="decide('approve')"><Check />批准</button>
          </template>
          <button v-else class="btn btn-primary" type="button" :disabled="busy" @click="simulate"><Play />{{ flow.state === 'failed' ? '重新开始模拟' : '开始模拟' }}</button>
        </div>
      </section>
      <!-- 纯文本模型：确认后一直显示 -->
      <div v-if="d.text_only && d.status !== 'text_only'" class="warn block" role="status"><AlertTriangle /><div><b>{{ TEXT_ONLY_NOTE }}。</b></div></div>

      <!-- 资料充分程度：分析后一直显示 -->
      <div v-if="d.material && d.material.level !== 'complete'" class="warn block material" role="status">
        <AlertTriangle /><div>
          <button type="button" class="material-toggle" :aria-expanded="materialOpen" @click="materialOpen = !materialOpen">{{ d.material.level === 'limited' ? '资料很少，参考性有限' : '资料不全，参考性有限' }} · 缺少 {{ d.material.gaps.length }} 项 · {{ materialOpen ? '收起' : '查看' }}</button>
          <template v-if="materialOpen">
            <p>{{ d.material.summary }}</p>
            <ul><li v-for="g in d.material.gaps" :key="g.item">缺少 {{ g.item }}：{{ g.effect }}</li></ul>
            <span v-if="d.site && d.site.status !== 'ok'" class="faint">首页没有读取成功（{{ d.site.reason }}），AI 只能依据你填写的内容。</span>
            <span v-else-if="d.site?.note" class="faint">{{ d.site.note }}。</span>
          </template>
        </div>
      </div>

      <ScoutPanel v-if="d.status === 'configuring' || d.valid" :scout="d.scout" />

      <!-- 确认人数与天数 -->
      <section v-if="d.status === 'configuring'" class="grid g2 top">
        <section class="panel">
          <div class="panel-head"><h3>产品模型</h3><span class="aside faint">{{ d.site?.status === 'ok' ? `已读取首页：${d.site.title || d.site.url}` : '未读取首页' }}</span></div>
          <template v-if="d.product">
            <p>{{ d.product.positioning }}</p>
            <p class="faint">目标用户：{{ d.product.target_users }}</p>
            <ul class="feats"><li v-for="f in (featuresOpen ? features : features.slice(0, 5))" :key="f">{{ f }}</li></ul>
            <button v-if="features.length > 5" class="btn btn-ghost sm" type="button" :aria-expanded="featuresOpen" @click="featuresOpen = !featuresOpen">{{ featuresOpen ? '收起功能' : '显示全部 ' + features.length + ' 项功能' }}</button>
            <p v-if="d.product.assumptions?.length" class="faint">假设与推断：{{ d.product.assumptions.join('；') }}</p>
          </template>
        </section>
        <section class="panel size">
          <div class="panel-head"><h3><Users class="hi" />人数与天数</h3><span class="aside faint">主 Agent 推荐，可以修改</span></div>
          <p v-if="d.recommendation" class="rationale">推荐 {{ d.recommendation.persona_count }} 人、{{ d.recommendation.duration_days }} 天：{{ d.recommendation.reason }}</p>
          <div class="size-row">
            <label class="field">人数<input v-model.number="size.count" class="input num" type="number" :min="limits.personas[0]" :max="limits.personas[1]" aria-label="人数" @input="size.touched = true" /></label>
            <label class="field">天数<input v-model.number="size.days" class="input num" type="number" min="1" :max="limits.days[1]" aria-label="天数" @input="size.touched = true" /></label>
          </div>
          <p class="faint small">每人在时间线上某一天首次体验产品（分散到不同日子），之后按作息刷社区、讨论；时间片 60 分钟。人数 {{ limits.personas[0] }}–{{ limits.personas[1] }}<template v-if="d.minimum_personas">（关键流程至少需要 {{ d.minimum_personas }} 人）</template>，天数 1–{{ limits.days[1] }}。</p>
          <div v-if="d.generation_error" class="warn" role="alert"><AlertTriangle /><div>上次生成没有成功：{{ d.generation_error.type }}{{ d.generation_error.status_code ? `（HTTP ${d.generation_error.status_code}）` : '' }}。可以直接重试，或换个人数。</div></div>
          <div v-if="sizeError" class="warn" role="alert"><AlertTriangle /><div>{{ sizeError }}</div></div>
          <div v-if="actionError" class="warn" role="alert"><AlertTriangle /><div>{{ actionError }}</div></div>
          <div class="row end"><button class="btn btn-primary" type="button" :disabled="busy || !!sizeError" @click="generate"><Users />生成人物</button></div>
        </section>
      </section>

      <!-- 模型不支持识图：确认后才继续分析 -->
      <section v-else-if="d.status === 'text_only'" class="panel" role="alert">
        <div class="panel-head"><h3>模型不支持图像识别</h3></div>
        <div class="warn listed"><AlertTriangle /><div><b>{{ TEXT_ONLY_NOTE }}。</b>
          <ul><li>人物浏览时只读取页面的文字和结构，不发送截图；排版错乱、图片缺失、颜色对比不足这类视觉问题发现不了。</li>
            <li>录像和截图照常保存，供你回放核对。</li>
            <li>这次运行的列表、审核页和报告都会标注“参考性有限”。</li></ul></div></div>
        <div v-if="actionError" class="warn" role="alert"><AlertTriangle /><div>{{ actionError }}</div></div>
        <div class="row end">
          <RouterLink class="btn btn-ghost" to="/new">换模型，新建运行</RouterLink>
          <button class="btn btn-primary" type="button" :disabled="busy" @click="acceptTextOnly">接受并继续分析</button>
        </div>
      </section>

      <!-- 分析中 / 生成中 / 失败 -->
      <section v-else-if="['analyzing', 'generating', 'failed', 'incomplete'].includes(d.status)" class="panel">
        <div class="panel-head"><h3>{{ { analyzing: '正在分析资料', generating: '正在生成人物草稿' }[d.status] ?? '没有完成' }}</h3>
          <RouterLink v-if="job" class="aside btn btn-ghost sm" :to="{ name: 'job', params: { jobId: job.id } }">任务详情</RouterLink>
        </div>
        <p v-if="d.status === 'analyzing'" class="row faint"><Loader class="spin" />{{ !job?.progress?.capability ? '正在准备能力文件' : !job?.progress?.site ? '正在读取首页' : !job?.progress?.product ? '正在生成产品模型' : !job?.progress?.scout ? '正在推荐人数与天数，并侦察网站（核对说明书，最长约 15 分钟）' : '正在推荐人数与天数' }}（每 3 秒刷新）</p>
        <p v-else-if="d.status === 'generating'" class="row faint"><Loader class="spin" />{{ job?.progress?.draft ? '草稿已写出，正在整理审核清单' : '正在规划人群分布并逐个补全人物（人多时需要较长时间）' }}（每 3 秒刷新）</p>
        <div v-else class="warn"><AlertTriangle /><div>{{ d.error ? `错误类型：${d.error.type}${d.error.status_code ? `（HTTP ${d.error.status_code}）` : ''}。` : '' }}运行目录里有 errors.log 记录详细原因；可以修正后新建一次运行。</div></div>
        <pre v-if="job?.log?.length" class="log">{{ job.log.join('\n') }}</pre>
      </section>

      <!-- 草稿不合法（例如手工改坏了） -->
      <section v-else-if="!d.valid" class="panel" role="alert">
        <div class="warn"><AlertTriangle /><div><b>草稿未通过校验，不能批准</b>：{{ d.error }}。修改运行目录里的 draft.json 后点“重新加载”。</div></div>
      </section>

      <template v-else>
        <div v-if="d.status === 'stale'" class="warn block"><AlertTriangle /><div><b>审批已失效</b>：{{ d.approval.reason }}。请重新审核。</div></div>
        <div v-if="d.blocked" class="warn block"><AlertTriangle /><div><b>不能批准</b>：{{ d.blocked }}</div></div>
        <div v-if="d.issues.length" class="warn block"><AlertTriangle /><div><b>人群分布与规划不一致</b>：{{ d.issues.join('；') }}。批准前需要勾选确认这些变更。</div></div>

        <div class="grid g2 top">
          <section class="panel">
            <div class="panel-head"><h3>产品模型</h3><span class="aside faint">{{ d.manual.url }}</span></div>
            <p>{{ d.product.positioning }}</p>
            <p class="faint">目标用户：{{ d.product.target_users }}</p>
            <ul class="feats"><li v-for="f in (featuresOpen ? features : features.slice(0, 5))" :key="f">{{ f }}</li></ul>
            <button v-if="features.length > 5" class="btn btn-ghost sm" type="button" :aria-expanded="featuresOpen" @click="featuresOpen = !featuresOpen">{{ featuresOpen ? '收起功能' : '显示全部 ' + features.length + ' 项功能' }}</button>
            <p class="faint">关键流程：{{ d.manual.flows.join('、') }}</p>
          </section>
          <section class="panel">
            <div class="panel-head"><h3>运行配置</h3><span class="aside faint num">{{ d.capability.model }}</span></div>
            <dl class="kv num">
              <dt>模拟起点</dt><dd>{{ d.run_config.start_time }}</dd>
              <dt>人数</dt><dd>{{ d.personas.length }} 人</dd>
              <dt>模拟时长</dt><dd class="days">
                <input v-model.number="days" class="input sm num" type="number" :min="latestDay" :max="limits.days[1]" aria-label="模拟天数" />天 · 每片 {{ d.run_config.time_slice_minutes }} 分钟
                <button v-if="days !== d.run_config.duration_days" class="btn btn-secondary sm" type="button" :disabled="busy || !Number.isInteger(days) || days < latestDay" @click="saveEdit({ duration_days: days }, '天数')">保存天数</button>
                <span v-if="Number.isInteger(days) && days < latestDay" class="neg small">有人排在第 {{ latestDay }} 天首次体验，不能少于 {{ latestDay }} 天</span>
              </dd>
              <dt>浏览并发上限</dt><dd>{{ d.run_config.max_concurrency }}（另受模型、浏览器与能力探测建议值限制）</dd>
            </dl>
            <div class="label">主 Agent 的分布方案</div>
            <p ref="rationaleEl" class="rationale" :class="{ clamped: !rationaleOpen }">{{ d.cohort_rationale }}</p>
            <button v-if="rationaleTruncated" class="btn btn-ghost sm" type="button" :aria-expanded="rationaleOpen" @click="rationaleOpen = !rationaleOpen">{{ rationaleOpen ? '收起方案' : '展开方案' }}</button>
            <ul class="dist"><li v-for="line in d.distribution" :key="line">{{ line.replace(/^- /, '') }}</li></ul>
          </section>
        </div>

        <section class="panel flush">
          <div class="panel-head pad"><h3>人物与时间表</h3><span class="aside faint">{{ d.personas.length }} 人 · 点击一行查看完整设定、修改采样参数</span></div>
          <div v-if="samplingNote" class="note pad-note"><Info />{{ samplingNote }}</div>
          <div class="table-wrap">
            <table class="data">
              <thead><tr><th>ID</th><th>姓名</th><th>年龄/性别</th><th>职业</th><th>设备/技术/耐心</th><th>动机</th><th>参与</th><th>体验日</th><th>本地体验时间</th><th>时间片</th><th>任务</th></tr></thead>
              <tbody>
                <template v-for="p in people" :key="p.persona_id">
                  <tr class="click" :aria-expanded="open === p.persona_id" @click="open = open === p.persona_id ? null : p.persona_id">
                    <td class="num">{{ p.persona_id }}</td><td><b>{{ p.realname }}</b></td><td class="num">{{ p.age }}/{{ p.gender }}</td><td>{{ p.profession }}</td>
                    <td>{{ label.device[p.browsing_profile.device] }}/{{ label.tech[p.browsing_profile.tech_level] }}/{{ label.patience[p.browsing_profile.patience] }}</td>
                    <td>{{ p.browsing_profile.motivation }}</td><td>{{ label.participation[p.participation] }}</td>
                    <td class="num">第 {{ p.schedule.browse_day ?? 1 }} 天</td><td class="num">{{ p.row.local_time }}</td><td class="num">{{ p.row.slice_index }}</td>
                    <td>{{ p.browsing_profile.assignment.flow ?? '自由探索' }}</td>
                  </tr>
                  <tr v-if="open === p.persona_id" class="detail">
                    <td colspan="11">
                      <p><b>{{ p.city }} · {{ p.timezone }}</b> · {{ p.bio }}</p>
                      <p>{{ p.persona }}</p>
                      <p class="faint">作息 {{ p.schedule.wake }}–{{ p.schedule.sleep }} · 体验时状态：{{ p.schedule.state_at_browse }} · 技术工具：{{ p.browsing_profile.tools.join('、') || '无' }} · 步数上限 {{ p.browsing_profile.max_steps }}</p>
                      <p class="faint">坦率程度 {{ p.disclosure.candor }} · 隐瞒倾向 {{ p.disclosure.withhold_tendency }}：{{ p.disclosure.withhold_reasons.join('；') }}</p>
                      <div class="label advanced">高级</div>
                      <div class="sampling" @click.stop>
                        <template v-if="editing[p.persona_id]">
                          <label>温度 temperature<input v-model.number="editing[p.persona_id].temperature" class="input sm num" type="number" step="0.01" min="0" max="2" /></label>
                          <label>top_p<input v-model.number="editing[p.persona_id].top_p" class="input sm num" type="number" step="0.01" min="0.01" max="1" /></label>
                          <label>presence_penalty<input v-model.number="editing[p.persona_id].presence_penalty" class="input sm num" type="number" step="0.05" min="-2" max="2" /></label>
                          <button class="btn btn-primary sm" type="button" :disabled="busy" @click="saveEdit({ sampling: { [p.persona_id]: editing[p.persona_id] } }, `${p.realname}的采样参数`)">保存</button>
                          <button class="btn btn-ghost sm" type="button" @click="editing = {}">取消</button>
                        </template>
                        <template v-else>
                          <span class="faint">采样参数（浏览、讨论、问卷与采访时用；由性格推出）：{{ p.sampling ? `温度 ${p.sampling.temperature} · top_p ${p.sampling.top_p} · presence_penalty ${p.sampling.presence_penalty}` : '未设置，用框架默认值' }}</span>
                          <button class="btn btn-ghost sm" type="button" @click="editSampling(p)">修改</button>
                        </template>
                      </div>
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
        </section>

        <section ref="actionsEl" class="panel actions">
          <p v-if="d.status === 'approved'" class="row"><Check class="ok" />已于 {{ new Date(d.approval.approved_at).toLocaleString('zh-CN', { hour12: false }) }} 批准<template v-if="d.approval.overrides.length">（含已确认的分布变更）</template>。</p>
          <p v-else class="faint row"><Info />手工修改运行目录里的 draft.json 后，点“重新加载”再审核；批准针对的是当前展示的版本。</p>
          <label v-if="canDecide && d.issues.length" class="row ov"><input v-model="overrides" type="checkbox" />我已核对，确认以上分布变更</label>
          <div v-if="actionError" class="warn" role="alert"><AlertTriangle /><div>{{ actionError }}</div></div>
          <div class="row end">
            <template v-if="canDecide">
              <button class="btn btn-danger" type="button" :disabled="rejectDisabled" @click="decide('reject')">拒绝</button>
              <button class="btn btn-primary" type="button" :disabled="approveDisabled" @click="decide('approve')"><Check />批准</button>
            </template>
            <button v-else-if="canSimulate" class="btn btn-primary" type="button" :disabled="busy" @click="simulate"><Play />{{ flow.state === 'failed' ? '重新开始模拟' : '开始模拟' }}</button>
          </div>
          <p v-if="d.simulations.length" class="faint sims">由这份草稿发起的模拟：
            <RouterLink v-for="s in d.simulations" :key="s" class="num" :to="{ name: 'report', params: { runId: s } }">{{ s }}</RouterLink>
          </p>
        </section>
      </template>
    </template>
  </div>
</template>

<style scoped>
.approval-summary { display: flex; align-items: center; justify-content: space-between; gap: var(--sp-4); flex-wrap: wrap; }
.summary-copy { min-width: 0; flex: 1; }
.summary-copy p { margin: var(--sp-1) 0 0; font-size: var(--fs-sm); overflow-wrap: anywhere; }
.summary-buttons { flex-shrink: 0; }
.material-toggle { padding: 0; border: 0; background: none; color: inherit; font: inherit; text-align: left; cursor: pointer; }
.clamped { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 3; overflow: hidden; }
.advanced { margin-top: var(--sp-3); }
@media (max-width: 1100px) { .summary-copy { flex-basis: 100%; } .top { grid-template-columns: 1fr; } }
.block { margin-bottom: var(--sp-4); }
.top { align-items: start; margin-bottom: var(--sp-4); }
.feats { margin: var(--sp-2) 0; padding-left: var(--sp-5); font-size: var(--fs-sm); }
.kv { display: grid; grid-template-columns: auto 1fr; gap: var(--sp-1) var(--sp-4); margin: 0 0 var(--sp-3); font-size: var(--fs-sm); }
.kv dt { color: var(--text-3); }
.kv dd { margin: 0; }
.rationale { font-size: var(--fs-sm); color: var(--text-2); line-height: 1.7; }
.dist { margin: 0; padding-left: var(--sp-5); font-size: var(--fs-xs); color: var(--text-2); line-height: 1.8; }
.pad { padding-top: 0; }
tr.click { cursor: pointer; }
tr.detail td { background: var(--surface-2); white-space: normal; font-size: var(--fs-sm); line-height: 1.7; }
tr.detail p { margin: 0 0 var(--sp-1); }
.actions { margin-top: var(--sp-4); }
.end { justify-content: flex-end; margin-top: var(--sp-3); }
.ov { font-size: var(--fs-sm); gap: var(--sp-2); }
.material ul, .listed ul { margin: var(--sp-1) 0; padding-left: var(--sp-5); }
.size { display: grid; gap: var(--sp-3); align-content: start; }
.size .panel-head { margin-bottom: 0; }
.size-row { display: flex; gap: var(--sp-4); flex-wrap: wrap; }
.field { display: grid; gap: 6px; font-size: var(--fs-sm); font-weight: 600; }
.field .input { width: 140px; }
.hi { width: 16px; height: 16px; stroke-width: 1.5; vertical-align: -3px; margin-right: 6px; }
.days { display: flex; align-items: center; gap: var(--sp-2); flex-wrap: wrap; }
.days .input { width: 80px; }
.pad-note { margin: var(--sp-3) 0 0; }
.sampling { display: flex; align-items: center; gap: var(--sp-3); flex-wrap: wrap; margin-top: var(--sp-2); cursor: default; }
.sampling label { display: grid; gap: 2px; font-size: var(--fs-xs); color: var(--text-3); }
.sampling .input { width: 96px; }
.small { font-size: var(--fs-xs); }
.ok { width: 16px; height: 16px; color: var(--pos); }
.sims { margin: var(--sp-3) 0 0; font-size: var(--fs-xs); display: flex; flex-wrap: wrap; gap: var(--sp-2); }
.log { background: var(--surface-2); border-radius: var(--r-md); padding: var(--sp-3); font-family: var(--font-mono); font-size: var(--fs-xs); max-height: 320px; overflow: auto; white-space: pre-wrap; margin: var(--sp-3) 0 0; }
.spin { width: 14px; height: 14px; animation: spin 1s linear infinite; stroke-width: 1.5; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
