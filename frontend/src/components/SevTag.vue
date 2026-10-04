<script setup>
import { label } from '../lib/sim.js'
defineProps({ sev: Number, highlight: Boolean })
</script>

<template>
  <span v-if="highlight" class="tag pos"><span class="dot"></span>亮点</span>
  <span v-else class="tag" :class="'sev' + sev"><span class="dot"></span>{{ label.sev[sev] }}</span>
</template>
