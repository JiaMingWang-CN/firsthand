<script setup>
// 说出的 / 未说出的 / 私下 · 问卷：三种样式只能按设计语言 8.3 使用
import PersonaChip from './PersonaChip.vue'
import SimTime from './SimTime.vue'
import EvTag from './EvTag.vue'
defineProps({
  kind: { type: String, default: 'public' }, // public | withheld | private
  pid: String, t: { type: Number, default: null }, action: String,
  text: String, reason: String, evidence: { type: Array, default: () => [] }, extra: String,
})
</script>

<template>
  <div class="voice" :class="kind">
    <div class="who">
      <PersonaChip :pid="pid" />
      <SimTime v-if="t != null" :m="t" />
      <span v-if="kind === 'public'">{{ action || '说出的' }}</span>
      <span v-else-if="kind === 'withheld'" class="kind">未说出的</span>
      <span v-else class="kind">私下 · 问卷</span>
    </div>
    <div class="text">{{ kind === 'withheld' ? text : `“${text}”` }}<span v-if="extra" class="extra num">{{ extra }}</span></div>
    <div v-if="reason || evidence.length" class="reason">
      <span v-if="reason">原因：{{ reason }}</span>
      <EvTag v-for="(ev, i) in evidence" :key="i" :ev="ev" />
    </div>
  </div>
</template>

<style scoped>
.text { line-height: 1.65; }
.extra { margin-left: var(--sp-2); color: var(--text-2); font-size: var(--fs-xs); }
</style>
