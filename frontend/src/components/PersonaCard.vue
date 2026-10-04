<script setup>
import { computed } from 'vue'
import { P, label, fmt, clockOf } from '../lib/sim.js'
import Avatar from './Avatar.vue'
import PartTag from './PartTag.vue'
const props = defineProps({ pid: String, compact: Boolean })
const p = computed(() => P[props.pid])
</script>

<template>
  <div class="persona-card">
    <Avatar :pid="pid" size="lg" />
    <div class="body">
      <div class="row nm"><span class="name">{{ p.realname }}</span><span class="sim-badge">模拟</span></div>
      <div class="sub">{{ p.age }} · {{ p.gender }} · {{ p.city }} · {{ p.profession }}</div>
      <div class="sub bg">{{ p.bio }}</div>
      <div class="attrs">
        <span class="tag">{{ label.device[p.device] }}</span>
        <span class="tag">{{ label.tech[p.tech] }}</span>
        <span class="tag">{{ label.patience[p.patience] }}</span>
        <span class="tag"><PartTag :kind="p.participation" /></span>
        <span class="simtime">◷ 体验 {{ fmt(p.slot) }}<template v-if="p.localSlot != null"> · 本地 {{ clockOf(p.localSlot) }}</template></span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.persona-card { display: grid; grid-template-columns: auto 1fr; gap: var(--sp-3); }
.body { min-width: 0; }
.nm { gap: var(--sp-2); flex-wrap: nowrap; }
.name { font-weight: 700; font-size: var(--fs-lg); line-height: 1.3; }
.sub { color: var(--text-2); font-size: var(--fs-sm); line-height: 1.6; }
.sub.bg { margin-top: 4px; }
.attrs { display: flex; flex-wrap: wrap; gap: 6px; margin-top: var(--sp-2); }
</style>
