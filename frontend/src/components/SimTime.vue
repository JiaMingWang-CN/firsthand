<script setup>
import { fmt } from '../lib/sim.js'
defineProps({ m: Number, prefix: { type: String, default: '' } })
</script>

<template>
  <span class="simtime"><span aria-hidden="true">◷</span>{{ prefix ? prefix + ' ' : '' }}{{ fmt(m) }}<span class="sr-only">（模拟时间）</span></span>
</template>
