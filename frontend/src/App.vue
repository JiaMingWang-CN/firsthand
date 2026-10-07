<script setup>
import { computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { clock, drawers, closeDrawer, confirmState, settleConfirm, togglePlay, seek } from './lib/store.js'
import { fmt, parseSim } from './lib/sim.js'
import { live } from './lib/data.js'
import { ensureRun } from './lib/live.js'
import AppNav from './components/AppNav.vue'
import RunBar from './components/RunBar.vue'
import DrawerHost from './components/DrawerHost.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import ToastHost from './components/ToastHost.vue'
import { STEPS, NOTES, WIDE, flowState, ROUTE_STEP } from './lib/shell.js'

const route = useRoute()
const router = useRouter()

// 报头与边注：日期行、当前所在的步骤、页面旁的补充说明
const dateline = `${new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' })} · 观察记录`
const at = computed(() => flowState.at ?? ROUTE_STEP[route.name] ?? null)
const folio = computed(() => (at.value != null ? `第 ${at.value + 1} 步，共 ${STEPS.length} 步 · ${STEPS[at.value]}${flowState.done ? ' · 已完成' : ''}` : route.params.runId ? '运行记录' : '工作台'))
const bignum = computed(() => (at.value != null ? String(at.value + 1).padStart(2, '0') : ''))
const notes = computed(() => NOTES[route.name] ?? [])
const wide = computed(() => WIDE.has(route.name))

// 带 runId 的页面先加载对应运行
const needsRun = computed(() => Boolean(route.params.runId))
watch(() => route.params.runId, () => { if (needsRun.value) ensureRun(String(route.params.runId)) }, { immediate: true })
const gate = computed(() => (!needsRun.value ? 'open' : live.id !== route.params.runId ? 'loading' : live.status))

// 时间联动：选中的模拟时刻同步到 URL（?t=D1-21:10）
watch([() => route.query.t, () => gate.value], ([q, ready]) => {
  // Wait for the requested run's span, not the previous run's clock or default one-day span.
  if (ready !== 'ready') return
  const m = parseSim(String(q || ''))
  if (m != null && Math.abs(m - clock.t) > 1) seek(m)
}, { immediate: true })
let urlTimer = 0
// Also on becoming ready: a run that loads at the clock's previous value changes no minute.
watch([() => Math.floor(clock.t), () => gate.value], () => {
  clearTimeout(urlTimer)
  if (!route.meta.timeLinked || gate.value !== 'ready') return
  const runId = route.params.runId
  urlTimer = setTimeout(() => {
    if (gate.value !== 'ready' || route.params.runId !== runId || !route.meta.timeLinked) return
    const t = fmt(Math.floor(clock.t)).replace(' ', '-')
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
onBeforeUnmount(() => { clearTimeout(urlTimer); window.removeEventListener('keydown', onKey) })
</script>

<template>
  <div class="frame">
    <AppNav />
    <div class="sheet">
      <header class="masthead"><span>{{ dateline }}</span><span class="folio">{{ folio }}</span></header>
      <template v-if="gate === 'open' || gate === 'ready'">
        <RunBar v-if="route.meta.runBar" />
      </template>
      <div class="sheet-body" :class="{ wide }">
        <main class="sheet-main">
          <div v-if="bignum" class="bignum" aria-hidden="true">{{ bignum }}</div>
          <template v-if="gate === 'open' || gate === 'ready'">
            <RouterView v-slot="{ Component }">
              <Transition name="fade" mode="out-in"><component :is="Component" :key="route.name" /></Transition>
            </RouterView>
          </template>
          <div v-else-if="gate === 'error'" class="page gate" role="alert">
            <h1 class="page-title">无法打开这次运行</h1>
            <p class="gate-msg">{{ live.error }}</p>
            <div class="row"><button class="btn btn-secondary" type="button" @click="ensureRun(String(route.params.runId))">重试</button>
              <RouterLink class="btn btn-ghost" to="/runs">返回运行列表</RouterLink></div>
          </div>
          <div v-else class="page gate" role="status" aria-live="polite"><p class="faint">正在读取运行数据…</p></div>
        </main>
        <aside v-if="notes.length" class="margin" aria-label="边注">
          <h4>边注</h4>
          <p v-for="n in notes" :key="n">{{ n }}</p>
          <p class="sig">muchhuman · 模拟数据，不代表真实用户</p>
        </aside>
      </div>
    </div>
    <DrawerHost />
    <ConfirmDialog />
    <ToastHost />
  </div>
</template>

<style>
.gate { max-width: 640px; }
.gate-msg { color: var(--text-2); line-height: 1.7; word-break: break-word; }
.frame { position: relative; z-index: 1; display: grid; grid-template-columns: 248px minmax(0, 1fr); min-height: 100vh; }
.sheet { min-width: 0; position: relative; transition: margin-right var(--dur-slow) var(--ease); }
/* 报头：日期行 + 双线 */
.masthead { display: flex; justify-content: space-between; gap: 16px; padding: 14px 48px 10px; border-bottom: 3px double var(--ink); font: 12px var(--font-mono); color: var(--text-2); }
.masthead .folio { color: var(--text-3); }
/* 正文与边注 */
.sheet-body { display: grid; grid-template-columns: minmax(0, 1fr) 280px; gap: 0 56px; padding: 40px 48px 110px; }
.sheet-body:not(:has(.margin)) { grid-template-columns: minmax(0, 1fr); }
.sheet-main { position: relative; min-width: 0; }
/* 标题后面的大号章节数字 */
.bignum { position: absolute; right: 0; top: -36px; font: 700 168px/1 var(--font-serif); color: var(--ink); opacity: .06; z-index: -1; pointer-events: none; user-select: none; letter-spacing: -.04em; }
.margin { position: sticky; top: 24px; align-self: start; border-left: 1px solid var(--border); padding: 4px 0 0 20px; font: 14px/1.75 var(--font-serif); color: var(--text-2); }
.margin h4 { font: 600 11px var(--font-mono); letter-spacing: .14em; color: var(--text-3); margin: 0 0 10px; }
.margin p { margin: 0 0 16px; }
.margin p::before { content: "※ "; color: var(--signal); font-family: var(--font-sans); }
.margin .sig { font: 12px var(--font-mono); color: var(--text-3); border-top: 1px solid var(--border); padding-top: 10px; margin-top: 18px; }
.margin .sig::before { content: none; }
/* 分栏多的页面：边注只在很宽的屏幕上出现；抽屉打开时也让位 */
.sheet-body.wide { grid-template-columns: minmax(0, 1fr) 240px; }
@media (max-width: 1500px) { .sheet-body.wide { grid-template-columns: minmax(0, 1fr); } .wide .margin { display: none; } }
@media (min-width: 1280px) { body.has-drawer .sheet { margin-right: var(--drawer-w, 480px); } }
body.has-drawer .sheet-body { grid-template-columns: minmax(0, 1fr); }
body.has-drawer .margin { display: none; }
@media (max-width: 1100px) {
  .frame { grid-template-columns: 1fr; }
  .sheet-body { grid-template-columns: 1fr; padding: 28px 20px 80px; }
  .masthead { padding: 10px 20px; }
  .margin { position: static; border-left: 0; border-top: 1px solid var(--border); padding: 16px 0 0; margin-top: 40px; }
  .bignum { font-size: 110px; top: -20px; }
}
</style>
