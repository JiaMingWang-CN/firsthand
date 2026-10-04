<script setup>
import { ref, watch, nextTick } from 'vue'
import { confirmState, settleConfirm } from '../lib/store.js'
const btn = ref(null)
watch(() => confirmState.open, async (o) => { if (o) { await nextTick(); btn.value?.focus() } })
</script>

<template>
  <Transition name="fade">
    <div v-if="confirmState.open" class="scrim" @click.self="settleConfirm(false)" @keydown.esc="settleConfirm(false)">
      <div class="dlg" role="alertdialog" aria-modal="true" :aria-label="confirmState.title">
        <h3>{{ confirmState.title }}</h3>
        <p>{{ confirmState.body }}</p>
        <div class="acts">
          <button class="btn btn-ghost" type="button" @click="settleConfirm(false)">返回</button>
          <button ref="btn" class="btn" :class="confirmState.danger ? 'btn-danger' : 'btn-primary'" type="button" @click="settleConfirm(true)">{{ confirmState.confirmText }}</button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.scrim { position: fixed; inset: 0; z-index: 80; background: color-mix(in srgb, var(--text) 30%, transparent); display: grid; place-items: center; padding: var(--sp-4); }
.dlg { width: min(460px, 100%); background: var(--surface); border-radius: var(--r-lg); box-shadow: var(--shadow-2); padding: var(--sp-5); border: 1px solid var(--border); }
h3 { font-size: var(--fs-lg); line-height: 1.5; }
p { color: var(--text-2); font-size: var(--fs-sm); margin: var(--sp-2) 0 var(--sp-5); }
.acts { display: flex; justify-content: flex-end; gap: var(--sp-2); }
</style>
