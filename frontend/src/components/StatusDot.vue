<script setup>
import { label } from '../lib/sim.js'
defineProps({ status: String })
</script>

<template>
  <span class="status" :class="'st-' + status"><i></i>{{ label.status[status] }}</span>
</template>
