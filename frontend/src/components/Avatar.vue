<script setup>
import { computed } from 'vue'
import { P } from '../lib/sim.js'
const props = defineProps({ pid: String, size: { type: String, default: '' } })
const p = computed(() => P[props.pid])
const lurker = computed(() => p.value.participation === 'lurker')
</script>

<template>
  <span
    class="avatar" :class="[size, { lurker }]"
    :style="lurker ? { color: p.color } : { background: p.color }"
    :title="`${p.realname}（模拟人物）`" aria-hidden="true"
  >{{ p.realname[0] }}</span>
</template>
