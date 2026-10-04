<script setup>
import { toasts } from '../lib/store.js'
import { Check } from 'lucide-vue-next'
</script>

<template>
  <div class="toasts" aria-live="polite">
    <TransitionGroup name="rise">
      <div v-for="t in toasts.list" :key="t.id" class="toast"><Check />{{ t.text }}
        <button v-if="t.action" class="act" type="button" @click="t.action.run">{{ t.action.label }}</button>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toasts { position: fixed; left: 50%; bottom: var(--sp-5); transform: translateX(-50%); z-index: 90; display: grid; gap: var(--sp-2); justify-items: center; }
.toast { display: flex; align-items: center; gap: var(--sp-2); background: var(--text); color: var(--bg); padding: var(--sp-2) var(--sp-4); border-radius: var(--r-md); font-size: var(--fs-sm); box-shadow: var(--shadow-2); }
.toast svg { width: 16px; height: 16px; stroke-width: 1.5; }
.act { background: none; border: none; color: var(--bg); text-decoration: underline; cursor: pointer; font-weight: 600; }
</style>
