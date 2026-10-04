<script setup>
// 情绪曲线：横轴步骤，纵轴受挫 → 满意，零线居中；困惑度用点的大小表示（设计语言第 13 节）
import { computed, ref, inject } from 'vue'
import { steps } from '../mock/data.js'
import { P, fmt } from '../lib/sim.js'
import { openDrawer } from '../lib/store.js'

const props = defineProps({
  pids: { type: Array, required: true },
  title: String,
  activeStep: { type: Number, default: 0 }, // 1 基
  upTo: { type: Number, default: Infinity }, // 只画到某个模拟时刻
  height: { type: Number, default: 150 },
})
const inDrawer = inject('inDrawer', false)
const asTable = ref(false)
const W = 560
const padL = 34, padR = 12, padT = 12, padB = 22
const H = computed(() => props.height)
const maxSteps = computed(() => Math.max(...props.pids.map((p) => steps[p].length)))
const x = (i) => padL + (i / Math.max(1, maxSteps.value - 1)) * (W - padL - padR)
const y = (sat) => padT + ((1 - sat) / 2) * (H.value - padT - padB)

const series = computed(() => props.pids.map((pid) => {
  const pts = steps[pid].map((s, i) => ({ i, s, x: x(i), y: y(s.sat), r: 2.5 + s.conf * 6 })).filter((p) => p.s.t <= props.upTo)
  return { pid, color: P[pid].color, pts, d: pts.map((p, k) => `${k ? 'L' : 'M'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ') }
}))
const single = computed(() => props.pids.length === 1)
const summary = computed(() => series.value.map((s) => {
  if (!s.pts.length) return `${P[s.pid].realname}：尚未开始`
  const low = s.pts.reduce((a, b) => (b.s.sat < a.s.sat ? b : a))
  return `${P[s.pid].realname}：${s.pts.length} 步，最低点在第 ${low.i + 1} 步（${low.s.act}）`
}).join('；'))

function open(pid, i) { openDrawer({ type: 'evidence', ev: { pid, step: i + 1, kind: 'step' } }, { fromDrawer: inDrawer }) }
</script>

<template>
  <div class="ec">
    <div class="head">
      <span class="label">{{ title || '情绪曲线' }}</span>
      <button class="btn btn-ghost sm" type="button" @click="asTable = !asTable">{{ asTable ? '查看图表' : '查看表格' }}</button>
    </div>
    <svg v-if="!asTable" :viewBox="`0 0 ${W} ${H}`" width="100%" role="img" :aria-label="`情绪曲线。${summary}`">
      <line :x1="padL" :x2="W - padR" :y1="y(0)" :y2="y(0)" stroke="var(--border-strong)" stroke-dasharray="3 3" />
      <line :x1="padL" :x2="W - padR" :y1="y(1)" :y2="y(1)" stroke="var(--border)" />
      <line :x1="padL" :x2="W - padR" :y1="y(-1)" :y2="y(-1)" stroke="var(--border)" />
      <text :x="0" :y="y(1) + 4" class="ax">满意</text>
      <text :x="0" :y="y(0) + 4" class="ax">0</text>
      <text :x="0" :y="y(-1) + 4" class="ax">受挫</text>
      <text v-for="i in maxSteps" :key="i" v-show="maxSteps <= 16 || i % 2 === 1" :x="x(i - 1)" :y="H - 6" class="ax mid">#{{ i }}</text>
      <g v-for="s in series" :key="s.pid">
        <path :d="s.d" fill="none" :stroke="s.color" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
        <g v-for="p in s.pts" :key="p.i" class="pt" tabindex="0" role="button"
           :aria-label="`${P[s.pid].realname} 第 ${p.i + 1} 步：${p.s.act}`"
           @click="open(s.pid, p.i)" @keydown.enter="open(s.pid, p.i)">
          <circle v-if="single" :cx="p.x" :cy="p.y" :r="p.r + 3" fill="var(--confused)" :opacity="p.s.conf > .3 ? .28 : 0" />
          <circle :cx="p.x" :cy="p.y" :r="activeStep === p.i + 1 && single ? 5.5 : 3.5" :fill="s.color" stroke="var(--surface)" stroke-width="1.5" />
          <title>#{{ p.i + 1 }} {{ fmt(p.s.t) }} · {{ p.s.act }}</title>
        </g>
      </g>
      <g v-if="single && activeStep">
        <line :x1="x(activeStep - 1)" :x2="x(activeStep - 1)" :y1="padT" :y2="H - padB" stroke="var(--accent)" stroke-width="1" stroke-dasharray="2 3" />
      </g>
    </svg>
    <div v-else class="table-wrap tbl">
      <table class="data compact">
        <thead><tr><th>人物</th><th class="r">步骤</th><th>模拟时间</th><th>动作</th><th class="r">满意度</th><th class="r">困惑度</th></tr></thead>
        <tbody>
          <template v-for="s in series" :key="s.pid">
            <tr v-for="p in s.pts" :key="p.i" @click="open(s.pid, p.i)">
              <td>{{ P[s.pid].realname }}</td><td class="r num">#{{ p.i + 1 }}</td><td class="num">{{ fmt(p.s.t) }}</td>
              <td class="act">{{ p.s.act }}</td><td class="r num">{{ p.s.sat.toFixed(1) }}</td><td class="r num">{{ p.s.conf.toFixed(1) }}</td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
    <div class="source">来源：体验记录 · {{ pids.length }} 名人物 · 点的光晕表示困惑度 · 点击某一步打开证据</div>
  </div>
</template>

<style scoped>
.head { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--sp-1); }
.ax { font-size: 10px; fill: var(--text-3); font-family: var(--font-mono); }
.ax.mid { text-anchor: middle; }
.pt { cursor: pointer; outline: none; }
.pt:hover circle:last-of-type, .pt:focus-visible circle:last-of-type { r: 6; }
.tbl { max-height: 260px; overflow: auto; border: 1px solid var(--border); border-radius: var(--r-md); }
.act { white-space: normal; min-width: 200px; }
</style>
