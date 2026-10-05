<script setup>
// 任务进度：后端按步骤执行命令行的同一套模块，进度来自运行目录里已经写出的文件（timeline.json、各阶段结果）。
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api/client.js'
import { AlertTriangle, Check, Loader, X, Circle } from 'lucide-vue-next'

const route = useRoute()
const jobId = computed(() => String(route.params.jobId))
const state = ref({ status: 'loading', job: null, error: '' })
let timer = 0

async function load() {
  clearTimeout(timer)
  try {
    const job = await api.job(jobId.value)
    state.value = { status: 'ready', job, error: '' }
    if (job.state === 'running') timer = setTimeout(load, 2000)
  } catch (e) {
    state.value = { status: 'error', job: null, error: e.message }
  }
}
watch(jobId, load, { immediate: true })
onBeforeUnmount(() => clearTimeout(timer))

const job = computed(() => state.value.job)
const p = computed(() => job.value?.progress ?? {})
const STATE = { running: ['confused', '进行中'], succeeded: ['pos', '已完成'], failed: ['neg', '失败'],
  detached: ['confused', '无法跟踪'] }
const stepIcon = { pending: Circle, running: Loader, succeeded: Check, failed: X }
const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0)
const when = (iso) => (iso ? new Date(iso).toLocaleString('zh-CN', { hour12: false }) : '—')
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <div class="eyebrow">任务 · <span class="num">{{ jobId }}</span></div>
        <h1 class="page-title">{{ job?.kind === 'simulate' ? '模拟与报告' : '生成人物草稿' }}</h1>
        <p class="page-sub">任务在后端以子进程执行与命令行相同的步骤；页面每 2 秒读取一次运行目录里的进度。关闭页面不会中断任务。</p>
      </div>
      <span v-if="job" class="tag" :class="STATE[job.state]?.[0]"><span class="dot"></span>{{ STATE[job.state]?.[1] ?? job.state }}</span>
    </header>

    <div v-if="state.status === 'loading'" class="panel"><p class="faint">正在读取任务…</p></div>
    <div v-else-if="state.status === 'error'" class="panel" role="alert"><p>{{ state.error }}</p></div>
    <template v-else>
      <div v-if="job.state === 'detached'" class="warn block"><AlertTriangle /><div>这个任务由之前的 API 进程启动，API 重启后无法再跟踪它的子进程；它可能仍在后台运行。下面的进度仍按运行目录里的文件显示。</div></div>

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
            <li :class="{ ok: p.capability }"><Check v-if="p.capability" /><Circle v-else />能力文件</li>
            <li :class="{ ok: p.draft }"><Check v-if="p.draft" /><Circle v-else />人物草稿</li>
          </ul>
          <div class="row links">
            <RouterLink class="btn btn-secondary sm" :to="{ name: 'review', params: { draftId: job.draft } }">{{ job.state === 'succeeded' ? '去审核' : '查看草稿' }}</RouterLink>
          </div>
        </template>
        <p class="faint small">开始于 {{ when(job.created_at) }}<template v-if="job.finished_at"> · 结束于 {{ when(job.finished_at) }}</template></p>
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
.bar { height: 6px; background: var(--surface-2); border-radius: 3px; overflow: hidden; }
.bar i { display: block; height: 100%; background: var(--sim); transition: width var(--dur-slow) var(--ease); }
.neg { color: var(--neg); }
.checks { list-style: none; padding: 0; margin: 0 0 var(--sp-3); display: flex; gap: var(--sp-4); font-size: var(--fs-sm); }
.checks li { display: flex; align-items: center; gap: 6px; color: var(--text-3); }
.checks li.ok { color: var(--text); }
.links { gap: var(--sp-2); margin: var(--sp-3) 0; }
.small { font-size: var(--fs-xs); margin: var(--sp-2) 0 0; }
.log { background: var(--surface-2); border-radius: var(--r-md); padding: var(--sp-3); font-family: var(--font-mono); font-size: var(--fs-xs); max-height: 420px; overflow: auto; white-space: pre-wrap; margin: 0; }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
