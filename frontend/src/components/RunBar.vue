<script setup>
import { computed } from 'vue'
import { personas, run, timeline } from '../lib/data.js'
import { fmt, statusAt } from '../lib/sim.js'
import { clock, SPEEDS, togglePlay } from '../lib/store.js'
import { Play, Pause } from 'lucide-vue-next'

const progress = computed(() => clock.t / timeline.total)
const counts = computed(() => {
  const c = { browse: 0, social: 0, done: 0, quit: 0, err: 0, wait: 0 }
  for (const p of personas) c[statusAt(p.id, clock.t)]++
  return c
})
const total = computed(() => run.usage?.total ?? {})
const num = (n) => (n ?? 0).toLocaleString('zh-CN')
const usageLine = (m) => `${m.model}：输入 ${num(m.input_tokens)}（缓存 ${num(m.cached_input_tokens)}）· 输出 ${num(m.output_tokens)}`
const usageTip = computed(() => {
  const lines = (run.usage?.models ?? []).map(usageLine)
  const iv = run.interviewUsage?.total
  if (iv?.requests) lines.push(`采访另计 ${num(iv.requests)} 次请求：输入 ${num(iv.input_tokens)}（缓存 ${num(iv.cached_input_tokens)}）· 输出 ${num(iv.output_tokens)}`)
  return lines.join(String.fromCharCode(10))
})
</script>

<template>
  <div class="runbar" role="region" aria-label="运行状态栏">
    <div class="clock">
      <span class="lbl">模拟时钟（UTC，距运行起点）</span>
      <span class="simtime big">◷ {{ fmt(clock.t) }}</span>
    </div>
    <div class="prog" :aria-label="`整体进度 ${Math.round(progress * 100)}%（模拟时间 ${fmt(clock.t)} / ${fmt(timeline.total)}）`">
      <div class="bar"><i :style="{ width: progress * 100 + '%' }"></i></div>
      <div class="pl">
        <span class="status st-browse" v-if="counts.browse"><i></i>体验中 {{ counts.browse }}</span>
        <span class="status st-social" v-if="counts.social"><i></i>在社区 {{ counts.social }}</span>
        <span class="status st-done"><i></i>已完成 {{ counts.done }}</span>
        <span class="status st-quit" v-if="counts.quit"><i></i>已放弃 {{ counts.quit }}</span>
        <span class="status st-err" v-if="counts.err"><i></i>出错 {{ counts.err }}</span>
        <span class="status st-wait"><i></i>等待中 {{ counts.wait }}</span>
      </div>
    </div>
    <div class="cost" :title="usageTip">
      <span class="lbl">模型用量 · 全程</span>
      <span class="num cv">{{ num(total.requests) }}<small> 次请求</small></span>
      <span class="num calls">输入 {{ num(total.input_tokens) }}（缓存 {{ num(total.cached_input_tokens) }}）· 输出 {{ num(total.output_tokens) }}</span>
    </div>
    <div class="ctl">
      <span class="replay">回放</span>
      <div class="seg" role="group" aria-label="回放速度">
        <button v-for="s in SPEEDS" :key="s.id" type="button" :aria-pressed="clock.speed === s.id" @click="clock.speed = s.id">{{ s.label }}</button>
      </div>
      <button class="btn btn-secondary icon" type="button" @click="togglePlay" :aria-label="clock.playing ? '暂停（空格）' : '播放（空格）'">
        <component :is="clock.playing ? Pause : Play" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.runbar {
  position: sticky; top: 0; z-index: 20; display: flex; align-items: center; gap: var(--sp-5);
  padding: var(--sp-2) var(--sp-6); min-height: 60px;
  background: color-mix(in srgb, var(--bg) 88%, transparent); backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--border);
}
.lbl { font-size: var(--fs-xs); color: var(--text-3); display: block; line-height: 1.3; }
.clock { flex: none; }
.simtime.big { font-size: var(--fs-sm); padding: 2px 8px; }
.prog { flex: 1; min-width: 180px; }
.bar { height: 4px; border-radius: 2px; background: var(--surface-2); overflow: hidden; }
.bar i { display: block; height: 100%; background: var(--sim); transition: width var(--dur) linear; }
.pl { display: flex; gap: var(--sp-4); margin-top: 6px; flex-wrap: wrap; }
.cost { flex: none; text-align: right; }
.cv { font-size: var(--fs-lg); font-weight: 600; display: block; line-height: 1.3; }
.cv small { font-size: var(--fs-xs); color: var(--text-3); font-weight: 400; }
.calls { font-size: var(--fs-xs); color: var(--text-3); }
.ctl { display: flex; align-items: center; gap: var(--sp-2); flex: none; }
.replay { font-size: var(--fs-xs); color: var(--text-3); border: 1px solid var(--border); border-radius: var(--r-sm); padding: 0 6px; }
@media (max-width: 1279px) { .runbar { padding: var(--sp-2) var(--sp-4); gap: var(--sp-3); } .calls, .replay { display: none; } }
@media (max-width: 959px) {
  .runbar { flex-wrap: wrap; top: 49px; }
  .prog { order: 3; flex-basis: 100%; }
  .pl { gap: var(--sp-3); }
  .seg { display: none; }
}
</style>
