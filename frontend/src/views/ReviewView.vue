<script setup>
// 运行前审核：与命令行 orchestrator.phase1 review 同一套规则、读写同一份审批记录。
// 批准时带上页面展示版本的哈希：展示后草稿被改过，后端会拒绝，要求重新加载再看一遍。
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/client.js'
import { label } from '../lib/sim.js'
import { askConfirm, toast } from '../lib/store.js'
import { AlertTriangle, Check, RefreshCw, Play, Info, Loader } from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()
const draftId = computed(() => String(route.params.draftId))
const state = ref({ status: 'loading', data: null, error: '' })
const job = ref(null) // 生成这份草稿的任务（生成中或失败时显示日志）
const overrides = ref(false)
const busy = ref(false)
const actionError = ref('')
const open = ref(null)
let timer = 0

async function load() {
  clearTimeout(timer)
  try {
    const data = await api.draft(draftId.value)
    state.value = { status: 'ready', data, error: '' }
    if (['generating', 'failed', 'incomplete'].includes(data.status)) {
      const jobs = await api.jobs()
      const mine = jobs.find((j) => j.kind === 'prepare' && j.draft === draftId.value)
      job.value = mine ? await api.job(mine.id) : null
    } else {
      job.value = null
    }
    if (data.status === 'generating') timer = setTimeout(load, 3000)
  } catch (e) {
    state.value = { status: 'error', data: null, error: e.message }
  }
}
watch(draftId, () => { state.value = { status: 'loading', data: null, error: '' }; overrides.value = false; load() }, { immediate: true })
onBeforeUnmount(() => clearTimeout(timer))

const d = computed(() => state.value.data)
const people = computed(() => {
  const rows = Object.fromEntries((d.value?.schedule ?? []).map((r) => [r.persona_id, r]))
  return (d.value?.personas ?? []).map((p) => ({ ...p, row: rows[p.persona_id] ?? {} }))
})
const STATUS = {
  generating: ['confused', '生成中'], failed: ['neg', '生成失败'], incomplete: ['neg', '生成未完成'],
  pending: ['', '待审核'], approved: ['pos', '已批准'], rejected: ['neg', '已拒绝'], stale: ['confused', '审批已失效'],
}
const status = computed(() => STATUS[d.value?.status] ?? ['', d.value?.status])
const canDecide = computed(() => d.value?.valid && ['pending', 'stale', 'rejected'].includes(d.value.status))

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
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <div class="eyebrow">运行前审核 · <span class="num">{{ draftId }}</span></div>
        <h1 class="page-title">{{ d?.manual?.name ?? d?.product ?? '运行前审核' }}</h1>
        <p class="page-sub">人物与运行配置在执行前需要人工确认。规则与命令行审核相同：批准的是页面展示的这一版；人群分布与规划不一致时，需要明确确认这些变更。</p>
      </div>
      <div class="row">
        <span v-if="d" class="tag" :class="status[0]"><span class="dot"></span>{{ status[1] }}</span>
        <button class="btn btn-secondary" type="button" :disabled="busy" @click="load"><RefreshCw />重新加载</button>
      </div>
    </header>

    <div v-if="state.status === 'loading'" class="panel"><p class="faint">正在读取草稿…</p></div>
    <div v-else-if="state.status === 'error'" class="panel" role="alert"><p>{{ state.error }}</p></div>

    <template v-else>
      <!-- 生成中 / 失败 -->
      <section v-if="['generating', 'failed', 'incomplete'].includes(d.status)" class="panel">
        <div class="panel-head"><h3>{{ d.status === 'generating' ? '正在生成人物草稿' : '人物草稿没有生成成功' }}</h3>
          <RouterLink v-if="job" class="aside btn btn-ghost sm" :to="{ name: 'job', params: { jobId: job.id } }">任务详情</RouterLink>
        </div>
        <p v-if="d.status === 'generating'" class="row faint"><Loader class="spin" />{{ job?.progress?.capability ? (job?.progress?.draft ? '草稿已写出，正在整理审核清单' : '能力文件就绪，正在生成产品模型与人物') : '正在准备能力文件' }}（每 3 秒刷新）</p>
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
            <ul class="feats"><li v-for="f in d.product.features" :key="f">{{ f }}</li></ul>
            <p class="faint">关键流程：{{ d.manual.flows.join('、') }}</p>
          </section>
          <section class="panel">
            <div class="panel-head"><h3>运行配置</h3><span class="aside faint num">{{ d.capability.model }}</span></div>
            <dl class="kv num">
              <dt>模拟起点</dt><dd>{{ d.run_config.start_time }}</dd>
              <dt>模拟时长</dt><dd>{{ d.run_config.duration_days }} 天 · 每片 {{ d.run_config.time_slice_minutes }} 分钟</dd>
              <dt>浏览并发上限</dt><dd>{{ d.run_config.max_concurrency }}（另受模型、浏览器与能力探测建议值限制）</dd>
            </dl>
            <div class="label">主 Agent 的分布方案</div>
            <p class="rationale">{{ d.cohort_rationale }}</p>
            <ul class="dist"><li v-for="line in d.distribution" :key="line">{{ line.replace(/^- /, '') }}</li></ul>
          </section>
        </div>

        <section class="panel flush">
          <div class="panel-head pad"><h3>人物与时间表</h3><span class="aside faint">{{ d.personas.length }} 人 · 点击一行查看完整设定</span></div>
          <div class="table-wrap">
            <table class="data">
              <thead><tr><th>ID</th><th>姓名</th><th>年龄/性别</th><th>职业</th><th>设备/技术/耐心</th><th>动机</th><th>参与</th><th>本地体验时间</th><th>时间片</th><th>任务</th></tr></thead>
              <tbody>
                <template v-for="p in people" :key="p.persona_id">
                  <tr class="click" :aria-expanded="open === p.persona_id" @click="open = open === p.persona_id ? null : p.persona_id">
                    <td class="num">{{ p.persona_id }}</td><td><b>{{ p.realname }}</b></td><td class="num">{{ p.age }}/{{ p.gender }}</td><td>{{ p.profession }}</td>
                    <td>{{ label.device[p.browsing_profile.device] }}/{{ label.tech[p.browsing_profile.tech_level] }}/{{ label.patience[p.browsing_profile.patience] }}</td>
                    <td>{{ p.browsing_profile.motivation }}</td><td>{{ label.participation[p.participation] }}</td>
                    <td class="num">{{ p.row.local_time }}</td><td class="num">{{ p.row.slice_index }}</td>
                    <td>{{ p.browsing_profile.assignment.flow ?? '自由探索' }}</td>
                  </tr>
                  <tr v-if="open === p.persona_id" class="detail">
                    <td colspan="10">
                      <p><b>{{ p.city }} · {{ p.timezone }}</b> · {{ p.bio }}</p>
                      <p>{{ p.persona }}</p>
                      <p class="faint">作息 {{ p.schedule.wake }}–{{ p.schedule.sleep }} · 体验时状态：{{ p.schedule.state_at_browse }} · 技术工具：{{ p.browsing_profile.tools.join('、') || '无' }} · 步数上限 {{ p.browsing_profile.max_steps }}</p>
                      <p class="faint">坦率程度 {{ p.disclosure.candor }} · 隐瞒倾向 {{ p.disclosure.withhold_tendency }}：{{ p.disclosure.withhold_reasons.join('；') }}</p>
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
        </section>

        <section class="panel actions">
          <p v-if="d.status === 'approved'" class="row"><Check class="ok" />已于 {{ new Date(d.approval.approved_at).toLocaleString('zh-CN', { hour12: false }) }} 批准<template v-if="d.approval.overrides.length">（含已确认的分布变更）</template>。</p>
          <p v-else class="faint row"><Info />手工修改运行目录里的 draft.json 后，点“重新加载”再审核；批准针对的是当前展示的版本。</p>
          <label v-if="canDecide && d.issues.length" class="row ov"><input v-model="overrides" type="checkbox" />我已核对，确认以上分布变更</label>
          <div v-if="actionError" class="warn" role="alert"><AlertTriangle /><div>{{ actionError }}</div></div>
          <div class="row end">
            <template v-if="canDecide">
              <button class="btn btn-danger" type="button" :disabled="busy || d.status === 'rejected'" @click="decide('reject')">拒绝</button>
              <button class="btn btn-primary" type="button" :disabled="busy || !!d.blocked || (d.issues.length > 0 && !overrides)" @click="decide('approve')"><Check />批准</button>
            </template>
            <button v-else-if="d.status === 'approved'" class="btn btn-primary" type="button" :disabled="busy" @click="simulate"><Play />开始模拟</button>
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
.block { margin-bottom: var(--sp-4); }
.top { align-items: start; margin-bottom: var(--sp-4); }
.feats { margin: var(--sp-2) 0; padding-left: var(--sp-5); font-size: var(--fs-sm); }
.kv { display: grid; grid-template-columns: auto 1fr; gap: var(--sp-1) var(--sp-4); margin: 0 0 var(--sp-3); font-size: var(--fs-sm); }
.kv dt { color: var(--text-3); }
.kv dd { margin: 0; }
.rationale { font-size: var(--fs-sm); color: var(--text-2); line-height: 1.7; }
.dist { margin: 0; padding-left: var(--sp-5); font-size: var(--fs-xs); color: var(--text-2); line-height: 1.8; }
.pad { padding: var(--sp-4) var(--sp-5) 0; }
tr.click { cursor: pointer; }
tr.detail td { background: var(--surface-2); white-space: normal; font-size: var(--fs-sm); line-height: 1.7; }
tr.detail p { margin: 0 0 var(--sp-1); }
.actions { margin-top: var(--sp-4); }
.end { justify-content: flex-end; margin-top: var(--sp-3); }
.ov { font-size: var(--fs-sm); gap: var(--sp-2); }
.ok { width: 16px; height: 16px; color: var(--pos); }
.sims { margin: var(--sp-3) 0 0; font-size: var(--fs-xs); display: flex; flex-wrap: wrap; gap: var(--sp-2); }
.log { background: var(--surface-2); border-radius: var(--r-md); padding: var(--sp-3); font-family: var(--font-mono); font-size: var(--fs-xs); max-height: 320px; overflow: auto; white-space: pre-wrap; margin: var(--sp-3) 0 0; }
.spin { width: 14px; height: 14px; animation: spin 1s linear infinite; stroke-width: 1.5; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
