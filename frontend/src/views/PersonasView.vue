<script setup>
import { ref, computed } from 'vue'
import { personas, steps, surveys } from '../lib/data.js'
import { statusAt, assignmentLabel, withheldFor, fmt } from '../lib/sim.js'
import { clock, openDrawer } from '../lib/store.js'
import { Search, LayoutGrid, Rows3 } from 'lucide-vue-next'
import PersonaCard from '../components/PersonaCard.vue'
import PersonaChip from '../components/PersonaChip.vue'
import StatusDot from '../components/StatusDot.vue'
import PartTag from '../components/PartTag.vue'
import PageIntro from '../components/PageIntro.vue'

const q = ref('')
const view = ref('table')
const coverageOpen = ref(false)
const filt = ref('all')
const filters = [
  ['all', '全部'], ['mobile', '手机'], ['developer', '开发者'], ['low', '低耐心'], ['quit', '已放弃'], ['unsaid', '有未说出的'],
]
const match = (p) => ({
  all: true, mobile: p.device === 'mobile', developer: p.tech === 'developer', low: p.patience === 'low',
  quit: p.outcome === 'quit', unsaid: withheldFor(p.id).length > 0,
}[filt.value])
const list = computed(() => personas.filter((p) => match(p) && (!q.value || [p.realname, p.profession, p.city, p.username].join(' ').includes(q.value.trim()))))
const count = (fn) => personas.filter(fn).length
// 分布要求（plan 4.4）按人数比例换算，与 orchestrator/personas.py 的 targets 一致；10 人即 2/4/3/2
const share = (f) => Math.floor(personas.length * f + 0.5)
const dist = computed(() => [
  { k: '开发者', v: count((p) => p.tech === 'developer'), min: Math.max(1, share(0.2)) },
  { k: '手机用户', v: count((p) => p.device === 'mobile'), min: share(0.4) },
  { k: '低耐心', v: count((p) => p.patience === 'low'), min: share(0.3) },
  { k: '明显的未说出倾向', v: count((p) => p.withhold === '高'), min: Math.max(1, share(0.2)) },
].map((d) => ({ ...d, ok: d.v >= d.min })))
const unmet = computed(() => dist.value.filter((d) => !d.ok))
const parts = computed(() => ['poster', 'commenter', 'reactor', 'lurker'].map((k) => ({ k, v: count((p) => p.participation === k) })))
const spark = (pid) => {
  const s = steps[pid]
  return s.map((x, i) => `${s.length > 1 ? (i / (s.length - 1)) * 100 : 50},${(1 - x.sat) * 14 + 2}`).join(' ')
}
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h1 class="page-title">人物</h1>
        <PageIntro>主 Agent 先用维度矩阵保证覆盖面，再补全身份、背景和性格。人设被换算成硬约束：设备、步数上限、停滞上限、体验时段和动作集合。</PageIntro>
      </div>
    </header>

    <div class="coverage-summary">
      <p :class="{ warning: unmet.length }">覆盖要求 {{ dist.length - unmet.length }}/{{ dist.length }} 已满足<template v-if="unmet.length"> · 未满足：{{ unmet.map((d) => d.k).join('、') }}</template><span class="participation"> · 参与方式：发帖 {{ parts[0].v }} · 评论 {{ parts[1].v }} · 点赞 {{ parts[2].v }} · 潜水 {{ parts[3].v }}</span></p>
      <button type="button" class="btn btn-ghost sm" :aria-expanded="coverageOpen" aria-controls="coverage-details" @click="coverageOpen = !coverageOpen">{{ coverageOpen ? '收起覆盖详情' : '查看覆盖详情' }}</button>
    </div>
    <div v-if="coverageOpen" id="coverage-details" class="grid dist">
      <div v-for="d in dist" :key="d.k" class="panel tight kpi" :class="{ warning: !d.ok }">
        <div class="k">{{ d.k }}</div><div class="v">{{ d.v }}<small>/{{ personas.length }}</small></div><div class="d">要求 ≥ {{ d.min }} · {{ d.ok ? '已满足' : '未满足' }}</div>
      </div>
      <div class="panel tight kpi parts">
        <div class="k">参与方式</div>
        <div class="row pr"><span v-for="x in parts" :key="x.k" class="row"><PartTag :kind="x.k" /><b class="num">{{ x.v }}</b></span></div>
      </div>
    </div>

    <div class="toolbar">
      <label class="search"><Search /><input v-model="q" data-search class="input" placeholder="搜索名字、职业、城市（按 / 聚焦）" aria-label="搜索人物" /></label>
      <div class="seg" role="group" aria-label="筛选">
        <button v-for="[k, n] in filters" :key="k" type="button" :aria-pressed="filt === k" @click="filt = k">{{ n }}</button>
      </div>
      <span class="sp"></span>
      <span class="faint now">状态截至 <span class="simtime">◷ {{ fmt(clock.t) }}</span></span>
      <div class="seg" role="group" aria-label="视图">
        <button type="button" :aria-pressed="view === 'cards'" @click="view = 'cards'" aria-label="卡片"><LayoutGrid class="vi" /></button>
        <button type="button" :aria-pressed="view === 'table'" @click="view = 'table'" aria-label="列表"><Rows3 class="vi" /></button>
      </div>
    </div>

    <div v-if="view === 'cards'" class="grid g2 cards">
      <article v-for="p in list" :key="p.id" class="panel pc" tabindex="0" @click="openDrawer({ type: 'persona', pid: p.id })" @keydown.enter="openDrawer({ type: 'persona', pid: p.id })">
        <PersonaCard :pid="p.id" />
        <div class="foot">
          <div class="fc"><span class="label">任务</span><span>{{ assignmentLabel(p) }}</span></div>
          <div class="fc"><span class="label">结果</span><StatusDot :status="statusAt(p.id, clock.t)" /></div>
          <div class="fc"><span class="label">情绪</span>
            <svg viewBox="0 0 100 32" class="spark" preserveAspectRatio="none" aria-hidden="true">
              <line x1="0" x2="100" y1="16" y2="16" stroke="var(--border)" stroke-dasharray="2 2" />
              <polyline :points="spark(p.id)" fill="none" :stroke="p.color" stroke-width="1.6" vector-effect="non-scaling-stroke" />
            </svg>
          </div>
          <div class="fc"><span class="label">NPS</span><span class="num">{{ surveys[p.id].nps }}</span></div>
          <div class="fc" v-if="withheldFor(p.id).length"><span class="tag withheld">未说出 {{ withheldFor(p.id).length }}</span></div>
        </div>
      </article>
      <p v-if="!list.length" class="faint">没有符合条件的人物。</p>
    </div>

    <div v-else class="panel flush">
      <div class="table-wrap">
        <table class="data persona-list">
          <thead><tr><th>人物</th><th>身份</th><th>结果</th><th class="r">NPS</th><th>未说出</th></tr></thead>
          <tbody>
            <tr v-for="p in list" :key="p.id" tabindex="0" @click="openDrawer({ type: 'persona', pid: p.id })" @keydown.enter.self="openDrawer({ type: 'persona', pid: p.id })">
              <td><PersonaChip :pid="p.id" no-hover /></td>
              <td><span class="identity">{{ p.age }} · {{ p.city }} · {{ p.profession }}</span></td>
              <td><StatusDot :status="statusAt(p.id, clock.t)" /></td>
              <td class="r num">{{ surveys[p.id].nps }}</td>
              <td><span v-if="withheldFor(p.id).length" class="tag withheld">未说出 {{ withheldFor(p.id).length }}</span></td>
            </tr>
            <tr v-if="!list.length"><td colspan="5" class="faint">没有符合条件的人物。</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<style scoped>
.coverage-summary { display: flex; align-items: center; flex-wrap: wrap; gap: var(--sp-2); margin-bottom: var(--sp-4); font-size: var(--fs-sm); }
.coverage-summary p { margin: 0; }
.participation { color: var(--text-2); }
.warning, .warning .k, .warning .d { color: var(--signal); }
.coverage-summary .btn { margin-left: auto; }
.persona-list { table-layout: fixed; width: 100%; min-width: 620px; }
.persona-list th:first-child { width: 150px; }
.persona-list th:nth-child(3) { width: 100px; }
.persona-list th:nth-child(4) { width: 64px; }
.persona-list th:last-child { width: 110px; }
.identity { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-2); }
.dist { grid-template-columns: repeat(4, minmax(0, 1fr)) 1.6fr; margin-bottom: var(--sp-5); }
.pr { gap: var(--sp-4); margin-top: var(--sp-2); }
.pr b { font-size: var(--fs-lg); }
.toolbar .seg[aria-label="筛选"] { max-width: 100%; flex-wrap: wrap; }
.toolbar { display: flex; align-items: center; gap: var(--sp-3); flex-wrap: wrap; margin-bottom: var(--sp-4); }
.search { position: relative; display: flex; align-items: center; }
.search svg { position: absolute; left: 10px; width: 16px; height: 16px; color: var(--text-3); stroke-width: 1.5; }
.search .input { padding-left: 32px; width: 300px; }
.sp { flex: 1; }
.now { font-size: var(--fs-xs); }
.vi { width: 14px; height: 14px; stroke-width: 1.5; vertical-align: -2px; }
.cards { align-items: stretch; gap: var(--sp-5) var(--sp-6); }
.pc { cursor: pointer; display: flex; flex-direction: column; border-top: 1px solid var(--ink); padding-top: var(--sp-4); }
.pc:hover { background: color-mix(in srgb, var(--surface-2) 45%, transparent); }
.foot { display: flex; gap: var(--sp-5); flex-wrap: wrap; align-items: flex-end; border-top: 1px solid var(--border); margin-top: auto; padding-top: var(--sp-3); font-size: var(--fs-sm); }
.pc :deep(.persona-card) { margin-bottom: var(--sp-4); }
.pc :deep(.bg) { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }
.fc { display: flex; flex-direction: column; gap: 2px; }
.spark { width: 90px; height: 22px; }
@media (max-width: 1279px) { .dist { grid-template-columns: repeat(2, minmax(0, 1fr)); } .parts { grid-column: 1 / -1; } }
@media (max-width: 959px) { .search .input { width: 100%; } .search { flex: 1; } }
</style>
