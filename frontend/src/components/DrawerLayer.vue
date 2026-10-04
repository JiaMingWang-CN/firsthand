<script setup>
import { provide } from 'vue'
import EvidenceView from './EvidenceView.vue'
import PersonaProfile from './PersonaProfile.vue'
import FindingDetail from './FindingDetail.vue'
import PostDetail from './PostDetail.vue'
defineProps({ layer: Object })
provide('inDrawer', true)
</script>

<template>
  <EvidenceView v-if="layer.type === 'evidence'" :key="layer.ev.pid + layer.ev.step + layer.ev.kind" :ev="layer.ev" />
  <PersonaProfile v-else-if="layer.type === 'persona'" :key="layer.pid" :pid="layer.pid" :tab="layer.tab" />
  <FindingDetail v-else-if="layer.type === 'finding'" :key="layer.id" :id="layer.id" />
  <PostDetail v-else-if="layer.type === 'post'" :key="layer.id" :id="layer.id" :focus="layer.focus" />
</template>
