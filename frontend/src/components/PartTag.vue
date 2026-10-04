<script setup>
import { label } from '../lib/sim.js'
defineProps({ kind: String })
</script>

<template>
  <span class="part" :class="kind"><i></i>{{ label.participation[kind] }}</span>
</template>
