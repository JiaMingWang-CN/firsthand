<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client.js'
import { runList, loadRunList } from '../lib/live.js'
import { TEXT_ONLY_NOTE } from '../lib/sim.js'
import { Plus, ArrowUpDown } from 'lucide-vue-next'
import PageIntro from '../components/PageIntro.vue'

const router = useRouter()
onMounted(loadRunList)
const sorted = computed(() => [...runList.items].sort((a, b) => (b.started_at ?? '').localeCompare(a.started_at ?? '') || b.id.localeCompare(a.id)))
const when = (iso) => (iso ? new Date(iso).toLocaleString('zh-CN', { hour12: false }) : '—')
const minutes = (r) => (r.started_at && r.finished_at ? Math.round((Date.parse(r.finished_at) - Date.parse(r.started_at)) / 60000) : null)
const status = (r) => {
  if (r.status === 'completed_with_documented_recovery') return ['st-done', '已完成（含人工恢复）']
  if (r.passed) return ['st-done', '已完成']
  return r.status === 'interrupted_or_failed' ? ['st-quit', '中断'] : ['st-err', '未通过']
}
const report = (r) => r.reports.find((x) => x.passed && x.model_used) ?? r.reports[0] ?? null
const open = (r) => router.push({ name: 'report', params: { runId: r.id } })

// 进行中的任务与待审核的草稿：有任务在跑时每 3 秒刷新，任务结束后顺带刷新运行列表
const jobs = ref([])
const drafts = ref([])
let timer = 0
async function loadPipeline() {
  clearTimeout(timer)
  try {
    const wasRunning = jobs.value.some((j) => j.state === 'running')
    ;[jobs.value, drafts.value] = await Promise.all([api.jobs(), api.drafts()])
    const running = jobs.value.some((j) => j.state === 'running')
    if (wasRunning && !running) loadRunList()
    if (running) timer = setTimeout(loadPipeline, 3000)
  } catch (e) { /* 列表照常显示；任务区留空 */ }
}
onMounted(loadPipeline)
onBeforeUnmount(() => clearTimeout(timer))
const activeJobs = computed(() => jobs.value.filter((j) => j.state === 'running' || j.state === 'detached'))
// 每份草稿在流程里的位置与下一步（与流程条的 7 步编号一致）
const DRAFT = { analyzing: ['第 2/7 步', '分析中'], text_only: ['第 2/7 步', '模型不支持识图，待你确认是否继续'], configuring: ['第 3/7 步', '待你确认人数与天数'], generating: ['第 4/7 步', '生成人物中'],
  pending: ['第 5/7 步', '待你审核批准'], stale: ['第 5/7 步', '审批已失效，待重新批准'], approved: ['第 6/7 步', '已批准，待开始模拟'] }
const waiting = computed(() => drafts.value.filter((d) => d.status in DRAFT && !(d.status === 'approved' && d.simulated)))
const jobText = (j) => (j.kind === 'simulate'
  ? `模拟 · 时间片 ${j.progress.slices_done}/${j.progress.slices} · 完成体验 ${j.progress.personas_done}/${j.progress.personas}`
  : j.kind === 'prepare' ? '分析资料' : '生成人物') + (j.state === 'detached' ? ' · 协调进程失联，需确认后释放' : '')
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <div class="eyebrow">工作台</div>
        <h1 class="page-title">运行</h1>
        <PageIntro>每次运行让模拟人物按各自作息真实使用产品，在社区里讨论，再私下填写离场问卷。结论只来自亲身体验，并附证据。这里列出后端已完成阶段 4 的运行；新建的运行在完成前显示在“进行中”。</PageIntro>
      </div>
      <RouterLink to="/new" class="btn btn-primary"><Plus />新建运行</RouterLink>
    </header>

    <section v-if="activeJobs.length || waiting.length" class="panel pipe">
      <div class="panel-head"><h3>进行中</h3></div>
      <ul>
        <li v-for="j in activeJobs" :key="j.id"><span class="status st-browse"><i></i>任务</span>
          <RouterLink :to="{ name: 'job', params: { jobId: j.id } }">{{ jobText(j) }}</RouterLink><span class="faint num">{{ j.id }}</span></li>
        <li v-for="d in waiting" :key="d.id"><span class="status st-wait"><i></i>{{ DRAFT[d.status][1] }}</span><span class="faint num">{{ DRAFT[d.status][0] }}</span>
          <RouterLink :to="{ name: 'review', params: { draftId: d.id } }">{{ d.product ?? '人物草稿' }}</RouterLink>
          <span v-if="d.text_only" class="tag neg" :title="TEXT_ONLY_NOTE"><span class="dot"></span>参考性有限 · 纯文本模型</span><span class="faint num">{{ d.id }}</span></li>
      </ul>
    </section>

    <div v-if="runList.status === 'loading' || runList.status === 'idle'" class="panel"><p class="faint">正在读取运行列表…</p></div>
    <div v-else-if="runList.status === 'error'" class="panel" role="alert">
      <p>{{ runList.error }}</p>
      <button class="btn btn-secondary" type="button" @click="loadRunList">重试</button>
    </div>
    <div v-else-if="!sorted.length" class="panel"><p class="faint">后端的运行目录里还没有完成阶段 4 的运行。</p></div>
    <section v-else class="panel flush">
      <div class="table-wrap">
        <table class="data">
          <thead>
            <tr>
              <th>状态</th><th>运行</th><th>开始时间 <ArrowUpDown class="si" /></th>
              <th class="r">用时</th><th class="r">人物</th><th>模型</th><th>报告</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in sorted" :key="r.id" @click="open(r)" tabindex="0" @keydown.enter="open(r)">
              <td><span class="status" :class="status(r)[0]"><i></i>{{ status(r)[1] }}</span></td>
              <td><b>{{ r.product ?? '（未知产品）' }}</b>
                <span v-if="r.text_only" class="tag neg tx" :title="TEXT_ONLY_NOTE"><span class="dot"></span>参考性有限 · 纯文本模型</span>
                <div class="faint num rid">{{ r.id }}</div></td>
              <td class="realtime">{{ when(r.started_at) }}</td>
              <td class="r num">{{ minutes(r) == null ? '—' : minutes(r) + ' 分钟' }}</td>
              <td class="r num">{{ r.personas }}</td>
              <td class="num">{{ [r.provider, r.model].filter(Boolean).join(' / ') || '—' }}</td>
              <td class="num">
                <template v-if="report(r)">问题 {{ report(r).issues ?? '—' }} · 亮点 {{ report(r).highlights ?? '—' }}<span v-if="r.reports.length > 1" class="faint"> · 共 {{ r.reports.length }} 份</span></template>
                <span v-else class="faint">无报告</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<style scoped>
.si { width: 12px; height: 12px; vertical-align: -2px; stroke-width: 1.5; }
.rid { font-size: var(--fs-xs); }
.tx { margin-left: var(--sp-2); }
.pipe { margin-bottom: var(--sp-6); }
.pipe ul { list-style: none; margin: 0; padding: 0; }
.pipe li { display: flex; align-items: center; gap: var(--sp-3); font-size: var(--fs-sm); flex-wrap: wrap; padding: 12px 0; border-bottom: 1px solid var(--border); }
td { white-space: normal !important; vertical-align: top; padding-top: 10px !important; padding-bottom: 10px !important; }
td.num { overflow-wrap: anywhere; min-width: 7em; }
td.realtime { white-space: nowrap !important; }
.pipe .faint { font-size: var(--fs-xs); }
</style>
