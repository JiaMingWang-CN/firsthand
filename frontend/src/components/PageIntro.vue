<script setup>
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const hidden = ref(false)
const storageKey = () => 'fh-page-intro-' + String(route.name)
watch(() => route.name, () => {
  hidden.value = false
  try { hidden.value = localStorage.getItem(storageKey()) === 'hidden' } catch (e) { /* 存储不可用时照常显示 */ }
}, { immediate: true })
function dismiss() {
  try {
    localStorage.setItem(storageKey(), 'hidden')
    hidden.value = true
  } catch (e) { /* 写入失败时保留介绍 */ }
}
</script>

<template>
  <div v-if="!hidden" class="page-intro">
    <p class="page-sub"><slot /></p>
    <button type="button" class="dismiss" aria-label="关闭页面介绍" @click="dismiss">×</button>
  </div>
</template>

<style scoped>
.page-intro { position: relative; padding-right: var(--sp-6); }
.dismiss { position: absolute; right: 0; top: 0; border: 0; background: none; color: var(--text-3); cursor: pointer; padding: 0 4px; font-size: var(--fs-lg); line-height: 1.5; }
.dismiss:hover { color: var(--text); }
</style>
