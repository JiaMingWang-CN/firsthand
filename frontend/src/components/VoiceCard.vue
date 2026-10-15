<script setup>
// 说出的 / 未说出的 / 私下 · 问卷：三种样式只能按设计语言 8.3 使用
import { ref } from 'vue'
import { useClamp } from '../lib/useClamp.js'
import PersonaChip from './PersonaChip.vue'
import SimTime from './SimTime.vue'
import EvTag from './EvTag.vue'
const props = defineProps({
  kind: { type: String, default: 'public' }, // public | withheld | private
  compact: Boolean,
  pid: String, t: { type: Number, default: null }, action: String,
  text: String, reason: String, evidence: { type: Array, default: () => [] }, extra: String,
})
const textEl = ref(null)
const reasonEl = ref(null)
const { expanded, truncated } = useClamp(
  () => props.compact ? [textEl.value, reasonEl.value] : [],
  () => [props.text, props.reason, props.extra, props.kind, props.compact],
)
</script>

<template>
  <div class="voice" :class="[kind, { compact }]">
    <div class="who">
      <PersonaChip :pid="pid" />
      <SimTime v-if="t != null" :m="t" />
      <span v-if="kind === 'public'">{{ action || '说出的' }}</span>
      <span v-else-if="kind === 'withheld'" class="kind">未说出的</span>
      <span v-else class="kind">私下 · 问卷</span>
    </div>
    <div ref="textEl" class="text" :class="{ clamped: compact && !expanded }">{{ kind === 'withheld' ? text : `“${text}”` }}<span v-if="extra" class="extra num">{{ extra }}</span></div>
    <div v-if="reason || evidence.length" class="reason">
      <span v-if="reason" ref="reasonEl" class="reason-text" :class="{ clamped: compact && !expanded }">原因：{{ reason }}</span>
      <EvTag v-for="(ev, i) in evidence" :key="i" :ev="ev" />
    </div>
    <button v-if="compact && truncated" type="button" class="btn btn-ghost sm quote-toggle" :aria-expanded="expanded" @click="expanded = !expanded">{{ expanded ? '收起引文' : '展开引文' }}</button>
  </div>
</template>

<style scoped>
.text { line-height: 1.65; }
.compact .text { overflow-wrap: anywhere; }
.clamped { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }
.compact { min-width: 0; font-size: var(--fs-sm); padding: var(--sp-2) var(--sp-3); }
.compact .who { gap: var(--sp-1) var(--sp-2); }
.compact .reason-text { width: 100%; overflow-wrap: anywhere; }
.quote-toggle { margin-top: var(--sp-1); font-family: var(--font-sans); }
.extra { margin-left: var(--sp-2); color: var(--text-2); font-size: var(--fs-xs); }
</style>
