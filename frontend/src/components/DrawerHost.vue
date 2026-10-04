<script setup>
import { ref, computed, watch } from 'vue'
import { drawers, closeDrawer, drawerBack } from '../lib/store.js'
import { X, ArrowLeft } from 'lucide-vue-next'
import DrawerLayer from './DrawerLayer.vue'

const width = ref(480)
const titles = { evidence: '证据', persona: '人物档案', finding: '发现', post: '帖子' }
watch(width, (w) => document.body.style.setProperty('--drawer-w', `${w}px`), { immediate: true })

function startResize(e) {
  const startX = e.clientX, startW = width.value
  const move = (ev) => { width.value = Math.max(480, Math.min(720, startW + (startX - ev.clientX))) }
  const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up) }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', up)
}
const layers = computed(() => drawers.stack)
</script>

<template>
  <TransitionGroup name="drawer" tag="div" class="drawer-host">
    <aside
      v-for="(layer, i) in layers" :key="i"
      class="drawer" :class="{ under: i < layers.length - 1 }"
      :style="{ width: width + 'px', right: i < layers.length - 1 ? '40px' : '0' }"
      role="dialog" :aria-label="titles[layer.type]" aria-modal="false"
    >
      <div class="resize" @pointerdown.prevent="startResize" title="拖动调整宽度（480–720）"></div>
      <header class="dh">
        <button v-if="layer.history.length" class="btn btn-ghost sm" type="button" @click="drawerBack(i)"><ArrowLeft />返回</button>
        <span class="dt">{{ titles[layer.type] }}<span v-if="i > 0" class="lvl num">· 第 2 层</span></span>
        <span class="sp"></span>
        <kbd>Esc</kbd>
        <button class="btn btn-ghost icon sm" type="button" aria-label="关闭" @click="closeDrawer(i)"><X /></button>
      </header>
      <div class="db">
        <DrawerLayer :layer="layer" />
      </div>
    </aside>
  </TransitionGroup>
</template>

<style scoped>
.drawer-host { position: fixed; top: 0; right: 0; bottom: 0; z-index: 40; pointer-events: none; }
.drawer {
  position: absolute; top: 0; bottom: 0; background: var(--surface); border-left: 1px solid var(--border);
  box-shadow: var(--shadow-2); display: flex; flex-direction: column; pointer-events: auto;
  transition: right var(--dur-slow) var(--ease), transform var(--dur-slow) var(--ease), opacity var(--dur-slow) var(--ease);
}
.drawer.under { filter: saturate(.7); }
.drawer.under::after { content: ""; position: absolute; inset: 0; background: color-mix(in srgb, var(--bg) 35%, transparent); pointer-events: none; }
.resize { position: absolute; left: -4px; top: 0; bottom: 0; width: 8px; cursor: ew-resize; z-index: 2; }
.resize:hover { background: linear-gradient(90deg, transparent 3px, var(--accent) 3px, var(--accent) 5px, transparent 5px); }
.dh { display: flex; align-items: center; gap: var(--sp-2); height: 52px; padding: 0 var(--sp-3) 0 var(--sp-5); border-bottom: 1px solid var(--border); flex: none; }
.dt { font-weight: 600; font-size: var(--fs-sm); }
.lvl { color: var(--text-3); font-weight: 400; margin-left: 6px; font-size: var(--fs-xs); }
.sp { flex: 1; }
.db { flex: 1; overflow-y: auto; padding: var(--sp-5); overscroll-behavior: contain; }
.drawer-enter-from, .drawer-leave-to { transform: translateX(100%); opacity: .4; }
@media (max-width: 959px) {
  .drawer { width: 100% !important; right: 0 !important; }
  .drawer.under { display: none; }
  .resize { display: none; }
}
</style>
