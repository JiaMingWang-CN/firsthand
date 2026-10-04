<script setup>
import { computed } from 'vue'
import { posts, withheld, steps } from '../lib/data.js'
import { findingById, F, P, fmt, strengthLabel } from '../lib/sim.js'
import { openDrawer } from '../lib/store.js'
import SevTag from './SevTag.vue'
import EvTag from './EvTag.vue'
import PersonaChip from './PersonaChip.vue'
import DotMatrix from './DotMatrix.vue'
import EmotionCurve from './EmotionCurve.vue'
import Shot from './Shot.vue'
import VoiceCard from './VoiceCard.vue'

const props = defineProps({ id: String })
const f = computed(() => findingById[props.id])
const hl = computed(() => f.value.kind === 'highlight')
const color = computed(() => (hl.value ? 'var(--pos)' : `var(--sev-${f.value.sev})`))
const evPids = computed(() => [...new Set(f.value.evidence.map((e) => e.pid))])
const evPidSet = computed(() => new Set(evPids.value))
// 关联的公开发言 / 未说出的：证据指向本发现涉及的人物
const relatedPublic = computed(() => posts
  .flatMap((p) => [{ id: p.id, author: p.author, t: p.t, body: p.title, evidence: p.evidence, isPost: true }, ...p.comments.map((c) => ({ ...c, isPost: false }))])
  .filter((x) => x.evidence.some((e) => evPidSet.value.has(e.pid) && f.value.affected.includes(x.author))))
const relatedWithheld = computed(() => withheld.filter((w) => f.value.affected.includes(w.pid) && w.evidence.some((e) => evPidSet.value.has(e.pid))))
const thumbs = computed(() => f.value.evidence.filter((e) => e.kind === 'step' || e.kind === 'shots').slice(0, 4))
const stepOf = (ev) => steps[ev.pid][ev.step - 1]
</script>

<template>
  <div>
    <div class="row">
      <SevTag :sev="f.sev" :highlight="hl" />
      <span class="tag">{{ f.flow ? F[f.flow].name : '跨流程' }}</span>
      <span v-if="!f.evidence.length" class="tag noev">无证据</span>
      <span class="sp"></span><span class="num faint fid">{{ f.id }}</span>
    </div>
    <h2 class="t">{{ f.title }}</h2>
    <p class="sum">{{ f.summary }}</p>
    <p v-if="f.cause" class="cause">{{ f.cause }}</p>

    <div class="panel tight kpis">
      <div><div class="label">受影响</div><DotMatrix :x="f.affected.length" :y="f.denominator" :color="color" /></div>
      <div v-if="f.unfinished?.length" title="报告只记录了这些人最终的结果，没有判断是否由这个问题导致"><div class="label">其中最终未完成体验</div><span class="num">{{ f.unfinished.length }}/{{ f.affected.length }}</span></div>
      <div v-if="!hl"><div class="label">证据强度</div><span>{{ strengthLabel(f.strength) }}</span></div>
    </div>

    <div class="sec">
      <div class="label">受影响的人物</div>
      <div class="row chips"><PersonaChip v-for="pid in f.affected" :key="pid" :pid="pid" /></div>
    </div>

    <div class="sec" v-if="f.evidence.length">
      <div class="label">证据 {{ f.evidence.length }} 条 · 点击在第 2 层打开</div>
      <div class="row chips"><EvTag v-for="(ev, i) in f.evidence" :key="i" :ev="ev" /></div>
      <div class="thumbs">
        <button v-for="(ev, i) in thumbs" :key="i" type="button" class="th" @click="openDrawer({ type: 'evidence', ev }, { fromDrawer: true })">
          <Shot compact :step="stepOf(ev)" :device="P[ev.pid].device" />
          <span class="cap num">{{ P[ev.pid].realname }} · #{{ ev.step }}</span>
        </button>
      </div>
    </div>
    <div v-else class="note" style="margin-top: var(--sp-4)">没有截图、步骤或轨迹能支撑这条记录。它不参与报告排序，只作为线索保留。</div>

    <div class="sec panel tight" v-if="evPids.length">
      <EmotionCurve :pids="evPids" :title="`相关人物的情绪曲线 · ${evPids.length} 人`" :height="140" />
      <div class="row lg"><span v-for="pid in evPids" :key="pid" class="li"><i :style="{ background: P[pid].color }"></i>{{ P[pid].realname }}</span></div>
    </div>

    <div class="sec" v-if="relatedPublic.length || relatedWithheld.length">
      <div class="label">相关的说出与未说出</div>
      <div class="voices">
        <VoiceCard v-for="x in relatedPublic" :key="x.id" kind="public" :pid="x.author" :t="x.t" :action="x.isPost ? '发帖' : '评论'" :text="x.body" />
        <VoiceCard v-for="(w, i) in relatedWithheld" :key="'w' + i" kind="withheld" :pid="w.pid" :t="w.t" :text="w.item" :reason="w.reason" :evidence="w.evidence" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.sp { flex: 1; }
.fid { font-size: var(--fs-xs); }
.t { font-size: var(--fs-xl); line-height: 1.4; margin: var(--sp-3) 0 var(--sp-2); }
.sum { color: var(--text-2); margin: 0 0 var(--sp-2); font-size: var(--fs-sm); }
.cause { color: var(--text-2); font-size: var(--fs-xs); background: var(--surface-2); border-radius: var(--r-md); padding: var(--sp-2) var(--sp-3); margin: 0; }
.kpis { display: flex; gap: var(--sp-6); margin-top: var(--sp-4); flex-wrap: wrap; font-size: var(--fs-sm); }
.sec { margin-top: var(--sp-5); }
.chips { margin-top: var(--sp-2); }
.thumbs { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--sp-3); margin-top: var(--sp-3); align-items: start; }
.th { border: none; background: none; padding: 0; cursor: pointer; text-align: left; }
.th :deep(.shot.m) { max-width: 130px; }
.th:hover :deep(.shot) { border-color: var(--accent); }
.cap { display: block; font-size: var(--fs-xs); color: var(--text-2); margin-top: 4px; }
.lg { gap: var(--sp-3); font-size: var(--fs-xs); color: var(--text-2); margin-top: var(--sp-2); }
.li { display: inline-flex; align-items: center; gap: 4px; }
.li i { width: 12px; height: 3px; border-radius: 2px; display: inline-block; }
.voices { display: grid; gap: var(--sp-2); margin-top: var(--sp-2); }
</style>
