<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { runs, run, personas, findings, withheld, steps } from '../mock/data.js'
import { socialEvents } from '../lib/sim.js'
import { taskedDone, tasked } from '../lib/sim.js'
import { Plus, FileText, Radio, ArrowUpDown } from 'lucide-vue-next'
import Avatar from '../components/Avatar.vue'
import DotMatrix from '../components/DotMatrix.vue'

const router = useRouter()
const sortKey = ref('when')
const sortDir = ref(-1)
const sorted = computed(() => [...runs].sort((a, b) => {
  const va = a[sortKey.value] ?? -1, vb = b[sortKey.value] ?? -1
  return (va > vb ? 1 : va < vb ? -1 : 0) * sortDir.value
}))
function sortBy(k) { if (sortKey.value === k) sortDir.value *= -1; else { sortKey.value = k; sortDir.value = -1 } }
function openRun(r) {
  router.push(r.status === 'review' ? { name: 'review', params: { runId: r.id } } : { name: 'report', params: { runId: 'run-20261003-b' } })
}
const statusMap = { completed: ['st-done', '已完成'], review: ['st-wait', '等待审核'], partial: ['st-quit', '部分完成'], running: ['st-browse', '运行中'] }
const trend = [...runs].filter((r) => r.s1 != null).reverse()
const maxIssues = Math.max(...trend.map((r) => r.s1 + r.s2))
const totalSteps = Object.values(steps).reduce((s, l) => s + l.length, 0)
const socialActs = socialEvents.filter((e) => e.kind !== 'read').length
const stages = [
  { k: '⓪', n: '能力探测', d: '识图 ✓ 工具调用 ✓' },
  { k: '①', n: '使用说明', d: '校验通过 · 4 条关键流程' },
  { k: '②', n: '侦察', d: '3 处与说明书不一致' },
  { k: '③', n: '人物与审核', d: '10 名人物 · 已确认' },
  { k: '④', n: '时间线模拟', d: `体验 ${totalSteps} 步 · 社区 ${socialActs} 次行动` },
  { k: '⑤', n: '离场问卷', d: '10/10 私下作答' },
  { k: '⑥', n: '报告', d: `${findings.length} 条发现 · 全部附证据` },
  { k: '⑦', n: '采访', d: '可追问任意人物' },
]
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <div class="eyebrow">工作台</div>
        <h1 class="page-title">运行</h1>
        <p class="page-sub">每次运行让 10 名模拟人物按各自作息真实使用你的产品，在社区里讨论，再私下填写离场问卷。结论只来自亲身体验，并附证据。</p>
      </div>
      <RouterLink to="/new" class="btn btn-primary"><Plus />新建运行</RouterLink>
    </header>

    <!-- 最近一次运行 -->
    <section class="panel latest">
      <div class="lt-main">
        <div class="row">
          <span class="status st-done"><i></i>已完成</span>
          <span class="realtime">{{ run.startedAt }} · 用时 {{ run.actual.minutes }} 分钟</span>
        </div>
        <h2 class="lt-title">{{ run.title }}</h2>
        <p class="lt-sum">模拟中 <b class="num">{{ taskedDone.length }}/{{ tasked.length }}</b> 名有任务的人物完成任务；发现 <b>2 个 S1 问题</b>；<b class="num">{{ withheld.length }}</b> 条体验没有在社区说出。</p>
        <div class="faces">
          <Avatar v-for="p in personas" :key="p.id" :pid="p.id" />
          <span class="sim-badge">模拟</span>
        </div>
        <div class="row acts">
          <RouterLink :to="{ name: 'report', params: { runId: run.id } }" class="btn btn-secondary"><FileText />查看报告</RouterLink>
          <RouterLink :to="{ name: 'live', params: { runId: run.id }, query: { t: 'D1-12:30' } }" class="btn btn-ghost"><Radio />回放运行现场</RouterLink>
        </div>
      </div>
      <div class="lt-kpis">
        <div class="kpi"><div class="k">任务完成</div><div class="v">{{ taskedDone.length }}<small>/{{ tasked.length }}</small></div><DotMatrix :x="taskedDone.length" :y="tasked.length" :show-text="false" /></div>
        <div class="kpi"><div class="k">S1 + S2 问题</div><div class="v">4</div><div class="d">较 v2.3 减少 2 个</div></div>
        <div class="kpi"><div class="k">实际花费</div><div class="v">¥{{ run.actual.cny }}</div><div class="d num">预估 ¥{{ run.estimate.min }}–{{ run.estimate.max }} · {{ run.actual.calls }} 次调用</div></div>
        <div class="kpi"><div class="k">证据</div><div class="v">{{ totalSteps }}<small> 步</small></div><div class="d">截图、轨迹、录像时间点</div></div>
      </div>
    </section>

    <!-- 流程 -->
    <section class="section">
      <div class="section-head"><h2>运行流程</h2><span class="aside">{{ run.id }} · 全部阶段已完成</span></div>
      <div class="layers">
        <div v-for="s in stages" :key="s.k" class="layer"><span class="k">{{ s.k }}</span><b>{{ s.n }}</b><p>{{ s.d }}</p></div>
      </div>
    </section>

    <div class="grid lower">
      <!-- 运行列表 -->
      <section class="panel flush">
        <div class="table-wrap">
          <table class="data">
            <thead>
              <tr>
                <th>状态</th><th>运行</th>
                <th class="sortable" @click="sortBy('when')">开始时间 <ArrowUpDown class="si" /></th>
                <th class="r">S1</th><th class="r">S2</th><th>任务完成</th>
                <th class="r sortable" @click="sortBy('cost')">费用 <ArrowUpDown class="si" /></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in sorted" :key="r.id" @click="openRun(r)" tabindex="0" @keydown.enter="openRun(r)">
                <td><span class="status" :class="statusMap[r.status][0]"><i></i>{{ statusMap[r.status][1] }}</span></td>
                <td><b>{{ r.title }}</b><div class="faint num rid">{{ r.id }}<span v-if="r.note"> · {{ r.note }}</span></div></td>
                <td class="realtime">{{ r.when }}</td>
                <td class="r num" :style="{ color: r.s1 ? 'var(--sev-1)' : '' }">{{ r.s1 ?? '—' }}</td>
                <td class="r num" :style="{ color: r.s2 ? 'var(--sev-2)' : '' }">{{ r.s2 ?? '—' }}</td>
                <td class="num">{{ r.done || '—' }}</td>
                <td class="r num">{{ r.cost ? '¥' + r.cost.toFixed(2) : '预估 ' + r.est }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- 版本趋势 -->
      <section class="panel">
        <div class="panel-head"><h3>版本之间的问题数</h3></div>
        <div class="trend" role="img" :aria-label="trend.map((r) => `${r.title}：S1 ${r.s1}，S2 ${r.s2}`).join('；')">
          <div v-for="r in trend" :key="r.id" class="tcol">
            <div class="stack" :style="{ height: ((r.s1 + r.s2) / maxIssues) * 120 + 'px' }">
              <i class="s2" :style="{ flex: r.s2 }"><span class="num">{{ r.s2 }}</span></i>
              <i class="s1" :style="{ flex: r.s1 }"><span class="num">{{ r.s1 }}</span></i>
            </div>
            <div class="tl num">{{ r.title.match(/v[\d.]+/)[0] }}</div>
            <div class="td realtime">{{ r.when.slice(5, 10) }}</div>
          </div>
        </div>
        <div class="row lg"><span class="tag sev1"><span class="dot"></span>S1 致命</span><span class="tag sev2"><span class="dot"></span>S2 严重</span></div>
        <div class="source">来源：各次运行的报告 · 每次 10 名人物 · 人物设定保持一致</div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.latest { display: grid; grid-template-columns: minmax(0, 1fr) 360px; gap: var(--sp-6); padding: var(--sp-6); }
.lt-title { font-size: var(--fs-2xl); line-height: 1.3; margin: var(--sp-3) 0 var(--sp-2); }
.lt-sum { color: var(--text-2); margin: 0; font-size: var(--fs-lg); max-width: 640px; }
.lt-sum b { color: var(--text); }
.faces { display: flex; align-items: center; margin: var(--sp-5) 0; }
.faces .avatar { margin-right: -6px; box-shadow: 0 0 0 2px var(--surface); }
.faces .avatar.lurker { background: var(--surface) !important; }
.faces .sim-badge { margin-left: var(--sp-4); }
.acts { gap: var(--sp-2); }
.lt-kpis { display: grid; grid-template-columns: 1fr 1fr; gap: var(--sp-5) var(--sp-4); border-left: 1px solid var(--border); padding-left: var(--sp-6); align-content: center; }
.layers { display: grid; grid-template-columns: repeat(8, minmax(0, 1fr)); }
.layer { padding: var(--sp-3) var(--sp-4) var(--sp-4); border: 1px solid var(--border); background: var(--surface); position: relative; margin-left: -1px; }
.layer:first-child { border-radius: var(--r-lg) 0 0 var(--r-lg); margin-left: 0; }
.layer:last-child { border-radius: 0 var(--r-lg) var(--r-lg) 0; }
.layer:not(:last-child)::after { content: "→"; position: absolute; right: -8px; top: 50%; transform: translateY(-50%); color: var(--text-3); background: var(--bg); font-size: 12px; z-index: 1; line-height: 1; padding: 2px 0; }
.layer .k { font-family: var(--font-mono); color: var(--text-3); font-size: var(--fs-sm); }
.layer b { display: block; font-size: var(--fs-sm); margin: 2px 0; }
.layer p { margin: 0; font-size: var(--fs-xs); color: var(--text-2); line-height: 1.5; }
.lower { grid-template-columns: minmax(0, 1fr) 340px; margin-top: var(--sp-6); align-items: start; }
.si { width: 12px; height: 12px; vertical-align: -2px; stroke-width: 1.5; }
.rid { font-size: var(--fs-xs); }
.trend { display: flex; align-items: flex-end; justify-content: space-around; height: 180px; border-bottom: 1px solid var(--border-strong); padding-bottom: 0; }
.tcol { display: flex; flex-direction: column; align-items: center; gap: 4px; position: relative; top: 44px; }
.stack { width: 36px; display: flex; flex-direction: column; border-radius: var(--r-sm) var(--r-sm) 0 0; overflow: hidden; }
.stack i { display: flex; align-items: center; justify-content: center; font-style: normal; font-size: var(--fs-xs); color: #fff; }
.stack .s1 { background: var(--sev-1); }
.stack .s2 { background: var(--sev-2); }
.tl { font-size: var(--fs-xs); font-weight: 600; margin-top: 6px; }
.td { font-size: 11px; }
.lg { margin-top: 56px; gap: var(--sp-2); }
@media (max-width: 1279px) {
  .layers { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--sp-2); }
  .layer, .layer:first-child, .layer:last-child { border-radius: var(--r-md); margin-left: 0; }
  .layer::after { display: none; }
  .lower, .latest { grid-template-columns: 1fr; }
  .lt-kpis { border-left: none; padding-left: 0; border-top: 1px solid var(--border); padding-top: var(--sp-5); }
}
@media (max-width: 959px) { .layers { grid-template-columns: 1fr 1fr; } .latest { padding: var(--sp-4); } }
</style>
