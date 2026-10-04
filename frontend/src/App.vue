<script setup>
import { watch, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { clock, drawers, closeDrawer, confirmState, settleConfirm, togglePlay, seek } from './lib/store.js'
import { fmt, parseSim } from './lib/sim.js'
import AppNav from './components/AppNav.vue'
import RunBar from './components/RunBar.vue'
import DrawerHost from './components/DrawerHost.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import ToastHost from './components/ToastHost.vue'

const route = useRoute()
const router = useRouter()

// 时间联动：选中的模拟时刻同步到 URL（?t=D1-21:10）
watch(() => route.query.t, (q) => {
  const m = parseSim(String(q || ''))
  if (m != null && Math.abs(m - clock.t) > 1) seek(m)
}, { immediate: true })
let urlTimer = 0
watch(() => Math.floor(clock.t), (m) => {
  if (!route.meta.timeLinked) return
  clearTimeout(urlTimer)
  urlTimer = setTimeout(() => {
    const t = fmt(m).replace(' ', '-')
    if (route.query.t !== t) router.replace({ query: { ...route.query, t } })
  }, clock.playing ? 600 : 150)
})

function onKey(e) {
  const typing = e.target.closest('input, textarea, select, [contenteditable]')
  if (e.key === 'Escape') {
    if (confirmState.open) return settleConfirm(false)
    if (drawers.stack.length) { closeDrawer(); e.preventDefault() }
    return
  }
  if (typing) return
  if (e.key === '/') {
    const s = document.querySelector('[data-search]')
    if (s) { s.focus(); e.preventDefault() }
  }
  if (e.key === ' ' && route.meta.runBar && !e.target.closest('button, a')) { togglePlay(); e.preventDefault() }
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="app">
    <AppNav />
    <div class="main">
      <RunBar v-if="route.meta.runBar" />
      <RouterView v-slot="{ Component }">
        <Transition name="fade" mode="out-in"><component :is="Component" :key="route.name" /></Transition>
      </RouterView>
    </div>
    <DrawerHost />
    <ConfirmDialog />
    <ToastHost />
  </div>
</template>

<style>
.app { display: grid; grid-template-columns: 240px minmax(0, 1fr); min-height: 100vh; }
.main { min-width: 0; transition: margin-right var(--dur-slow) var(--ease); }
@media (min-width: 1280px) { body.has-drawer .main { margin-right: var(--drawer-w, 480px); } }
@media (max-width: 1279px) and (min-width: 960px) { .app { grid-template-columns: 64px minmax(0, 1fr); } }
@media (max-width: 959px) { .app { grid-template-columns: 1fr; } }
</style>
