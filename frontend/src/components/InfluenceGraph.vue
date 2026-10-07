<script setup>
// 舆论动态：帖子 → 谁在什么时候看到 → 是否带着预期去体验
import { computed, ref } from 'vue'
import { personas, posts, reads } from '../lib/data.js'
import { P, fmt, browseStart, browseEnd } from '../lib/sim.js'
import { openDrawer } from '../lib/store.js'

const T0 = 600, T1 = 1440
const W = 880, rowH = 26, padL = 92, padR = 16, padT = 14
const order = [...personas].sort((a, b) => a.slot - b.slot).map((p) => p.id)
const H = padT + order.length * rowH + 28
const x = (t) => padL + ((Math.max(T0, t) - T0) / (T1 - T0)) * (W - padL - padR)
const yOf = (pid) => padT + order.indexOf(pid) * rowH + rowH / 2
const asTable = ref(false)

const postNodes = computed(() => posts.map((p) => ({ ...p, x: x(p.t), y: yOf(p.author) })))
const links = computed(() => reads.map((r) => {
  const post = posts.find((p) => p.id === r.post)
  const x1 = x(post.t), y1 = yOf(post.author), x2 = x(r.t), y2 = yOf(r.pid)
  const mx = (x1 + x2) / 2
  return { ...r, post, d: `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`, x2, y2, strong: !!r.expectation && r.t < browseStart(r.pid) }
}))
const strongCount = computed(() => links.value.filter((l) => l.strong).length)
</script>

<template>
  <div>
    <div class="head">
      <span class="label">帖子如何影响别人的预期 · {{ fmt(T0) }}–{{ fmt(T1) }}</span>
      <button class="btn btn-ghost sm" type="button" @click="asTable = !asTable">{{ asTable ? '查看图表' : '查看表格' }}</button>
    </div>
    <div v-if="!asTable" class="scroll">
      <svg :viewBox="`0 0 ${W} ${H}`" :width="W" role="img"
           :aria-label="`舆论动态图：3 条帖子共被看了 ${reads.length} 次，其中 ${strongCount} 次发生在读者体验产品之前并形成了预期。`">
        <g v-for="pid in order" :key="pid">
          <text :x="0" :y="yOf(pid) + 4" class="nm">{{ P[pid].realname }}</text>
          <line :x1="padL" :x2="W - padR" :y1="yOf(pid)" :y2="yOf(pid)" stroke="var(--border)" />
          <rect v-if="browseEnd(pid) > T0" :x="x(browseStart(pid))" :y="yOf(pid) - 4" :width="Math.max(4, x(browseEnd(pid)) - x(browseStart(pid)))" height="8" rx="2" :fill="P[pid].color" opacity=".9">
            <title>{{ P[pid].realname }} 体验 {{ fmt(browseStart(pid)) }}–{{ fmt(browseEnd(pid)) }}</title>
          </rect>
        </g>
        <g v-for="h in [10, 12, 14, 16, 18, 20, 22, 24]" :key="h">
          <line :x1="x(h * 60)" :x2="x(h * 60)" :y1="padT - 6" :y2="H - 22" stroke="var(--border)" stroke-dasharray="2 4" />
          <text :x="x(h * 60)" :y="H - 8" class="tk">{{ String(h).padStart(2, '0') }}:00</text>
        </g>
        <path v-for="(l, i) in links" :key="i" :d="l.d" fill="none" :stroke="P[l.post.author].color"
              :stroke-width="l.strong ? 2.2 : 1" :stroke-dasharray="l.strong ? '' : '3 3'" :opacity="l.strong ? .95 : .45">
          <title>{{ P[l.pid].realname }} 在 {{ fmt(l.t) }} 看了「{{ l.post.title }}」{{ l.strong ? ' · 体验前，形成预期' : '' }}</title>
        </path>
        <circle v-for="(l, i) in links" :key="'r' + i" :cx="l.x2" :cy="l.y2" :r="l.strong ? 4.5 : 3" fill="var(--surface)" :stroke="P[l.post.author].color" stroke-width="1.5" />
        <g v-for="n in postNodes" :key="n.id" class="node" tabindex="0" role="button" :aria-label="`打开帖子：${n.title}`"
           @click="openDrawer({ type: 'post', id: n.id })" @keydown.enter="openDrawer({ type: 'post', id: n.id })">
          <rect :x="n.x - 7" :y="n.y - 7" width="14" height="14" rx="3" :fill="P[n.author].color" stroke="var(--surface)" stroke-width="2" />
          <title>{{ P[n.author].realname }} 发帖 {{ fmt(n.t) }}：{{ n.title }}</title>
        </g>
      </svg>
    </div>
    <div v-else class="table-wrap tblw">
      <table class="data compact">
        <thead><tr><th>读者</th><th>模拟时间</th><th>帖子</th><th>是否在体验前</th><th>形成的预期</th></tr></thead>
        <tbody>
          <tr v-for="(l, i) in links" :key="i" @click="openDrawer({ type: 'post', id: l.post.id })">
            <td>{{ P[l.pid].realname }}</td><td class="num">{{ fmt(l.t) }}</td><td class="wrap">{{ l.post.title }}</td>
            <td>{{ l.t < browseStart(l.pid) ? '体验前' : '体验后' }}</td><td class="wrap">{{ l.expectation || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="legend">
      <span><i class="sq"></i>发帖</span><span><i class="ci"></i>看帖</span>
      <span><i class="ln strong"></i>体验前看到并形成预期（{{ strongCount }} 次）</span><span><i class="ln"></i>普通看帖</span>
      <span><i class="bar"></i>体验时段</span>
    </div>
    <div class="source">来源：看帖记录 {{ reads.length }} 条 · 社区帖子 {{ posts.length }} 条 · 颜色为发帖人</div>
  </div>
</template>

<style scoped>
.head { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--sp-2); }
.scroll { overflow-x: auto; }
svg { display: block; max-width: 100%; height: auto; min-width: 640px; }
.nm { font-size: 12px; fill: var(--text-2); }
.tk { font-size: 10px; fill: var(--text-3); font-family: var(--font-mono); text-anchor: middle; }
.node { cursor: pointer; outline: none; }
.node:hover rect, .node:focus-visible rect { stroke: var(--text); }
.legend { display: flex; flex-wrap: wrap; gap: var(--sp-4); font-size: var(--fs-xs); color: var(--text-3); margin-top: var(--sp-2); }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.sq { width: 10px; height: 10px; border-radius: 0; background: var(--text-2); display: inline-block; }
.ci { width: 9px; height: 9px; border-radius: 50%; border: 1.5px solid var(--text-2); display: inline-block; }
.ln { width: 18px; border-top: 1px dashed var(--text-2); display: inline-block; }
.ln.strong { border-top: 2px solid var(--text-2); }
.bar { width: 18px; height: 6px; border-radius: 0; background: var(--text-2); display: inline-block; }
.tblw { max-height: 300px; overflow: auto; border: 1px solid var(--border); border-radius: var(--r-md); }
.wrap { white-space: normal; min-width: 180px; }
</style>
