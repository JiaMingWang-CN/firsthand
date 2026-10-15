<script setup>
import { ref } from 'vue'
import EvTag from './EvTag.vue'
defineProps({ evidence: Array })
const open = ref(false)
</script>

<template>
  <div v-if="evidence.length" class="evidence-group">
    <button type="button" class="btn btn-ghost sm" :aria-expanded="open" @click="open = !open">证据 · {{ evidence.length }}</button>
    <div v-if="open" class="row evidence-items">
      <EvTag v-for="(ev, i) in evidence" :key="i" :ev="ev" />
    </div>
  </div>
</template>

<style scoped>
.evidence-group { font-family: var(--font-sans); }
.evidence-items { margin-top: var(--sp-2); }
</style>
