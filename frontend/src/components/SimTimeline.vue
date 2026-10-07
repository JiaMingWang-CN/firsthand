<script setup>
// 全局唯一的模拟时间轴（设计语言 8.4）。rows 模式下展开为每人一行。
import { computed, ref } from 'vue'
import { personas, steps, timeline } from '../lib/data.js'
import { P, fmt, browseStart, browseEnd, socialEvents } from '../lib/sim.js'
import { openDrawer } from '../lib/store.js'
import Avatar from './Avatar.vue'

const props = defineProps({
  modelValue: { type: Number, default: () => timeline.total },
  rows: Boolean,
  showActivity: Boolean,
  scrub: { type: Boolean, default: true },
  pids: { type: Array, default: () => personas.map((p) => p.id) },
})
const emit = defineEmits(['update:modelValue', 'scrub-start'])
const track = ref(null)
// 缩放：真实会话只有几分钟，全天视图里体验条很窄；缩放后以播放头为中心显示一段窗口
const ZOOMS = [{ id: 'day', label: '全天', len: Infinity }, { id: '2h', label: '2 小时', len: 120 }, { id: '30m', label: '30 分钟', len: 30 }]
const zoom = ref('day')
const view = computed(() => {
  const len = Math.min(timeline.total, ZOOMS.find((z) => z.id === zoom.value).len)
  return { from: Math.max(0, Math.min(timeline.total - len, props.modelValue - len / 2)), len }
})
const pct = (m) => `${((m - view.value.from) / view.value.len) * 100}%`
const inView = (m) => m >= view.value.from && m <= view.value.from + view.value.len
/** 区间与窗口的交集，不相交时为 null */
function clip(start, end) {
  const a = Math.max(start, view.value.from), b = Math.min(end, view.value.from + view.value.len)
  return b >= a ? { left: pct(a), width: pct(view.value.from + b - a) } : null
}
const slotOf = (pid) => browseStart(pid)
const endOf = (pid) => browseEnd(pid)

const events = computed(() => {
  const by = {}
  for (const e of socialEvents) if (e.kind !== 'read') (by[e.pid] ||= []).push(e)
  return by
})
const kindName = { post: '发帖', comment: '评论' }
const tickStep = computed(() => (view.value.len <= 30 ? 5 : view.value.len <= 120 ? 15 : view.value.len <= 1440 ? 180 : 360))
const ticks = computed(() => {
  const { from, len } = view.value, step = tickStep.value
  const out = []
  for (let t = Math.ceil(from / step) * step; t <= from + len; t += step) out.push(t)
  return out
})
const grid = computed(() => {
  const { from, len } = view.value, step = len < timeline.total ? tickStep.value : 60
  const out = []
  for (let t = Math.ceil(from / step) * step; t <= from + len; t += step) out.push(t)
  return out
})
const tickLabel = (t) => (t > 0 && t % 1440 === 0 ? `D${t / 1440} 24:00` : t >= 1440 ? fmt(t) : fmt(t).slice(3))

function toMinute(clientX) {
  const r = track.value.getBoundingClientRect()
  const minute = view.value.from + Math.max(0, Math.min(1, (clientX - r.left) / r.width)) * view.value.len
  return view.value.len < 120 ? Math.round(minute * 10) / 10 : Math.round(minute)
}
function down(e) {
  if (!props.scrub) return
  emit('scrub-start')
  emit('update:modelValue', toMinute(e.clientX))
  const move = (ev) => emit('update:modelValue', toMinute(ev.clientX))
  const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up) }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', up)
}
function key(e) {
  const step = e.shiftKey ? 60 : 10
  if (e.key === 'ArrowRight') { emit('update:modelValue', Math.min(timeline.total, props.modelValue + step)); e.preventDefault() }
  if (e.key === 'ArrowLeft') { emit('update:modelValue', Math.max(0, props.modelValue - step)); e.preventDefault() }
}
function openEvent(e) {
  if (e.kind === 'react') return
  const postId = e.kind === 'post' ? e.ref : e.post
  openDrawer({ type: 'post', id: postId, focus: e.ref })
}
</script>

<template>
  <div class="tl" :class="{ rows }">
    <div class="grid-wrap">
      <!-- 行标签 -->
      <div v-if="rows" class="labels">
        <div class="lh"></div>
        <div v-for="pid in pids" :key="pid" class="lrow">
          <Avatar :pid="pid" size="sm" /><span>{{ P[pid].realname }}</span>
        </div>
        <div class="lh"></div>
      </div>

      <div class="plot">
        <div class="track" ref="track" @pointerdown="down" :style="rows ? { '--rows': pids.length } : null">
          <div v-for="g in grid" :key="g" class="hline" :class="{ major: g % 360 === 0 }" :style="{ left: pct(g) }"></div>

          <!-- 折叠模式：头像标在体验起点 -->
          <template v-if="!rows">
            <span v-for="pid in pids.filter((x) => inView(slotOf(x)))" :key="pid" class="mark" :style="{ left: pct(slotOf(pid)) }" :title="`${P[pid].realname} · 体验 ${fmt(slotOf(pid))}`">
              <Avatar :pid="pid" size="sm" />
            </span>
          </template>

          <!-- 展开模式：每人一行 -->
          <template v-else>
            <div class="rowlane" v-for="(pid, i) in pids" :key="pid" :style="{ top: `${22 + i * 30}px` }">
              <template v-if="showActivity">
                <template v-for="h in P[pid].heat" :key="h.t">
                  <i v-if="clip(h.t, h.t + 60)" class="heat" :style="{ ...clip(h.t, h.t + 60), opacity: h.v * 0.28 }"></i>
                </template>
              </template>
              <i v-if="clip(slotOf(pid), endOf(pid))" class="browse" :style="{ ...clip(slotOf(pid), endOf(pid)), background: P[pid].color }" :title="`体验 ${fmt(slotOf(pid))}–${fmt(endOf(pid))}`"></i>
              <template v-if="view.len <= 120">
                <i v-for="s in steps[pid].filter((x) => inView(x.t))" :key="s.n" class="stepmark" :style="{ left: pct(s.t) }" :title="`步骤 #${s.n} · ${fmt(s.t)}`"></i>
              </template>
              <button v-for="e in (events[pid] || []).filter((x) => inView(x.t))" :key="e.ref + e.t" class="sdot" :class="e.kind" type="button"
                      :style="{ left: pct(e.t), color: P[pid].color }"
                      :title="`${kindName[e.kind]} · ${fmt(e.t)}`" :aria-label="`${P[pid].realname} ${kindName[e.kind]} ${fmt(e.t)}`"
                      @pointerdown.stop @click.stop="openEvent(e)"></button>
            </div>
          </template>

          <div class="ticks">
            <span v-for="t in ticks" :key="t" class="tick" :style="{ left: pct(t) }">{{ tickLabel(t) }}</span>
          </div>

          <div v-if="scrub" class="playhead" :style="{ left: pct(modelValue) }" tabindex="0" role="slider"
               aria-label="模拟时间播放头" :aria-valuetext="fmt(modelValue)" :aria-valuemin="0" :aria-valuemax="timeline.total" :aria-valuenow="Math.round(modelValue)"
               @keydown="key">
            <span class="ph-label" :class="{ flip: (modelValue - view.from) / view.len > 0.9 }">{{ fmt(modelValue) }}</span>
          </div>
        </div>
      </div>
    </div>
    <div v-if="rows" class="legend">
      <span><i class="lg-browse"></i>体验时段</span>
      <span><i class="lg post"></i>发帖</span>
      <span><i class="lg comment"></i>评论</span>
      <span v-if="showActivity"><i class="lg-heat"></i>刷社区概率</span>
      <span v-if="view.len <= 120"><i class="lg-step"></i>步骤</span>
      <span class="sp"></span>
      <div class="seg" role="group" aria-label="时间轴缩放">
        <button v-for="z in ZOOMS" :key="z.id" type="button" :aria-pressed="zoom === z.id" @click="zoom = z.id">{{ z.label }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tl { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg); padding: var(--sp-3) var(--sp-4); user-select: none; }
.grid-wrap { display: flex; gap: var(--sp-3); }
.labels { width: 92px; flex: none; }
.lh { height: 22px; }
.lrow { height: 30px; display: flex; align-items: center; gap: 6px; font-size: var(--fs-xs); white-space: nowrap; overflow: hidden; }
.plot { flex: 1; min-width: 0; }
.track { position: relative; height: 84px; cursor: col-resize; touch-action: none; }
.rows .track { height: auto; }
.rows .plot .track { height: calc(var(--rows, 10) * 30px + 50px); }
.night { position: absolute; top: 0; bottom: 22px; background: var(--surface-2); border-radius: var(--r-sm); }
.hline { position: absolute; top: 0; bottom: 22px; width: 1px; background: var(--border); opacity: .45; }
.hline.major { opacity: 1; }
.mark { position: absolute; bottom: 30px; transform: translateX(-50%); }
.mark:nth-child(odd) { bottom: 50px; }
.rowlane { position: absolute; left: 0; right: 0; height: 30px; }
.heat { position: absolute; top: 5px; height: 20px; background: var(--sim); display: block; }
.browse { position: absolute; top: 9px; height: 12px; min-width: 6px; border-radius: 0; display: block; }
.stepmark { position: absolute; top: 6px; width: 1px; height: 18px; background: var(--text); opacity: .55; display: block; pointer-events: none; }
.lg-step { width: 1px; height: 12px; background: var(--text-2); display: inline-block; }
.legend .sp { flex: 1; }
.sdot { position: absolute; top: 9px; width: 12px; height: 12px; margin-left: -6px; border-radius: 50%; border: 1.5px solid currentColor; background: var(--surface); padding: 0; cursor: pointer; }
.sdot.post { background: currentColor; }
.sdot.comment { background: linear-gradient(90deg, currentColor 50%, var(--surface) 50%); }
.sdot.react { background: radial-gradient(circle, currentColor 2px, var(--surface) 2.5px); cursor: default; }
.sdot:hover { transform: scale(1.25); }
.ticks { position: absolute; left: 0; right: 0; bottom: 0; height: 20px; border-top: 1px solid var(--border-strong); }
.tick { position: absolute; top: 3px; font-family: var(--font-mono); font-size: 10px; color: var(--text-3); transform: translateX(-50%); }
.tick:first-child { transform: none; }
.tick:last-child { transform: translateX(-100%); }
.playhead { position: absolute; top: -4px; bottom: 20px; width: 2px; margin-left: -1px; background: var(--sim); cursor: ew-resize; z-index: 3; }
.playhead::before { content: ""; position: absolute; left: -5px; top: -2px; width: 12px; height: 12px; border-radius: 50%; background: var(--sim); box-shadow: 0 0 0 3px var(--surface); }
.ph-label.flip { left: auto; right: 10px; }
.ph-label { position: absolute; top: -3px; left: 10px; font-family: var(--font-mono); font-size: 11px; color: var(--sim); background: var(--sim-soft); padding: 0 5px; border-radius: 0; white-space: nowrap; line-height: 16px; }
.legend { display: flex; flex-wrap: wrap; gap: var(--sp-4); margin-top: var(--sp-3); font-size: var(--fs-xs); color: var(--text-3); }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.lg-browse { width: 18px; height: 8px; border-radius: 0; background: var(--text-2); display: inline-block; }
.lg { width: 10px; height: 10px; border-radius: 50%; border: 1.5px solid var(--text-2); display: inline-block; }
.lg.post { background: var(--text-2); }
.lg.comment { background: linear-gradient(90deg, var(--text-2) 50%, transparent 50%); }
.lg.react { background: radial-gradient(circle, var(--text-2) 2px, transparent 2.5px); }
.lg-heat { width: 18px; height: 10px; background: var(--sim); opacity: .22; display: inline-block; }
.lg-night { width: 18px; height: 10px; background: var(--surface-2); border: 1px solid var(--border); display: inline-block; }
@media (max-width: 959px) { .labels { width: 28px; } .lrow span { display: none; } }
</style>
