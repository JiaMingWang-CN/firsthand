<script setup>
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { product, live, personas, timeline, run } from '../lib/data.js'
import { ui, toggleTheme } from '../lib/store.js'
import { usageTip } from '../lib/usage.js'
import { STEPS, flowState, ROUTE_STEP } from '../lib/shell.js'

const route = useRoute()
const runId = computed(() => route.params.runId)
const stepRoutes = { 5: 'live', 6: 'report', 7: 'interview' }
const extraLinks = [{ name: 'personas', label: '人物' }, { name: 'community', label: '社区' }]
const keepQuery = (name) => (['live', 'personas', 'community'].includes(name) && route.query.t ? { t: route.query.t } : {})
const ready = computed(() => live.id === runId.value && live.status === 'ready' && product.name)
// 当前在流程的哪一步：带流程条的页面以它为准，其余页面按路由固定对应
const at = computed(() => flowState.at ?? ROUTE_STEP[route.name] ?? null)
const stepClass = (i) => (at.value == null ? '' : i < at.value || (flowState.done && i === at.value) ? 'done' : i === at.value ? 'now' : '')
const popover = ref(null)
const popup = ref('')
const when = (iso) => (iso ? new Date(iso).toLocaleString('zh-CN', { hour12: false }) : '—')
function openPopover(name) {
  popup.value = name
  popover.value.showModal()
}
function closePopover() {
  if (!popover.value?.open) return false
  popover.value.close()
  popup.value = ''
  return true
}
function toggleShortcuts() {
  if (!closePopover()) openPopover('shortcuts')
}
function onPopoverKey(e) {
  if (e.key === 'Escape' || e.key === '?') { closePopover(); e.preventDefault() }
}
watch([() => route.name, runId], closePopover)
onBeforeUnmount(closePopover)
defineExpose({ closePopover, toggleShortcuts })
</script>

<template>
  <aside class="rail" aria-label="主导航">
    <div>
      <RouterLink to="/runs" class="mark" aria-label="亲历 首页">
        <svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" fill="var(--ink)"/><path d="M9 6.5V23l4.2-3.8 3 6.4 2.8-1.3-3-6.3 5.6-.4z" fill="var(--bg)"/><rect x="21" y="21" width="5" height="5" fill="var(--signal)"/></svg>
        <span>亲历</span><small>firsthand</small>
      </RouterLink>
      <div class="motto">让模拟的人先替你用一遍</div>
    </div>

    <nav aria-label="工作台">
      <RouterLink to="/runs" :class="{ on: route.name === 'runs' }">运行</RouterLink>
      <RouterLink to="/new" :class="{ on: route.name === 'new' }">新建运行</RouterLink>
    </nav>

    <div v-if="runId" class="cur">
      <h4>当前运行</h4>
      <div class="rmeta">
        <div class="product-line">
          <b>{{ ready ? product.name : '加载中…' }}</b>
          <button type="button" class="themebtn" @click="openPopover('details')">详情</button>
        </div>
        <div v-if="ready">{{ personas.length }} 人 · {{ Math.max(1, Math.round(timeline.total / 1440)) }} 天</div>
      </div>
    </div>

    <div class="rflow">
      <h4>流程</h4>
      <ol class="rsteps" :class="{ readonly: !runId }">
        <li v-if="runId" class="done prep"><span class="dot"></span><span class="prep-label"><span class="no">01–05</span> 准备</span></li>
        <template v-for="(s, i) in STEPS" :key="s">
          <li v-if="!runId || i >= 5" :class="stepClass(i)" :aria-current="i === at && !flowState.done ? 'step' : undefined">
            <span class="dot"></span><span class="no">{{ String(i + 1).padStart(2, '0') }}</span><RouterLink v-if="runId && stepRoutes[i]" :to="{ name: stepRoutes[i], params: { runId }, query: keepQuery(stepRoutes[i]) }" :title="stepRoutes[i] === 'live' ? '运行现场' : undefined">{{ s }}</RouterLink><span v-else>{{ s }}</span>
          </li>
        </template>
      </ol>
      <nav v-if="runId" class="extra-links" aria-label="运行数据">
        <RouterLink v-for="l in extraLinks" :key="l.name" :to="{ name: l.name, params: { runId }, query: keepQuery(l.name) }" :class="{ on: route.name === l.name }">{{ l.label }}</RouterLink>
      </nav>
    </div>

    <div class="rfoot">
      <button type="button" class="themebtn" @click="toggleShortcuts">? 快捷键</button>
      <button type="button" class="themebtn" @click="toggleTheme" :aria-label="ui.theme === 'dark' ? '切换到浅色主题' : '切换到深色主题'">{{ ui.theme === 'dark' ? '切换到浅色' : '切换到深色' }}</button>
    </div>
  </aside>
  <Teleport to="body">
    <dialog ref="popover" class="shell-popover" aria-labelledby="shell-popover-title" @cancel.prevent="closePopover" @keydown.stop="onPopoverKey">
      <div class="popover-head">
        <h2 id="shell-popover-title">{{ popup === 'details' ? '运行详情' : '快捷键' }}</h2>
        <button type="button" class="themebtn" aria-label="关闭浮层" autofocus @click="closePopover">×</button>
      </div>
      <template v-if="popup === 'details'">
        <dl class="details">
          <dt>运行 ID</dt><dd class="num">{{ runId }}</dd>
          <template v-if="ready">
            <template v-if="run.report"><dt>报告 ID</dt><dd class="num">{{ run.report.id }}</dd></template>
            <dt>起止时间</dt><dd>{{ when(run.startedAt) }} → {{ when(run.endedAt) }}</dd>
            <dt>提供方 / 模型</dt><dd>{{ run.model || '—' }}</dd>
            <dt>时间片长度</dt><dd>{{ timeline.sliceMinutes }} 分钟</dd>
            <template v-if="run.concurrency != null"><dt>浏览并发上限</dt><dd>{{ run.concurrency }}</dd></template>
            <dt>模型用量</dt><dd class="usage">{{ usageTip }}</dd>
          </template>
        </dl>
        <p v-if="!ready" class="faint">正在读取运行数据…</p>
      </template>
      <div v-else class="keys">
        <span><kbd>Esc</kbd> 关闭浮层或抽屉</span>
        <span><kbd>J</kbd><kbd>K</kbd> 切换报告问题</span>
        <span><kbd>/</kbd> 搜索</span>
        <span><kbd>空格</kbd> 播放或暂停（运行现场、社区）</span>
        <span><kbd>?</kbd> 打开或关闭快捷键</span>
      </div>
    </dialog>
  </Teleport>
</template>

<style scoped>
.rail { position: sticky; top: 0; height: 100vh; overflow-y: auto; border-right: 1px solid var(--ink); padding: 28px 26px 24px 24px; display: flex; flex-direction: column; gap: 26px; background: var(--surface-2); z-index: 1; }
/* 侧栏右缘的刻度尺 */
.rail::after { content: ""; position: absolute; top: 0; right: 0; width: 7px; height: 100%; pointer-events: none;
  background: repeating-linear-gradient(to bottom, var(--text-3) 0 1px, transparent 1px 12px), repeating-linear-gradient(to bottom, var(--ink) 0 1px, transparent 1px 60px);
  background-size: 4px 100%, 7px 100%; background-repeat: repeat-y; background-position: right top, right top; opacity: .45; }
.mark { display: inline-flex; align-items: center; gap: 10px; font: 700 22px/1 var(--font-serif); text-decoration: none; letter-spacing: .04em; }
.mark svg { width: 26px; height: 26px; flex: none; }
.mark small { font: 500 11px var(--font-mono); letter-spacing: .08em; color: var(--text-3); align-self: flex-end; margin-bottom: 1px; }
.motto { font: 12px var(--font-mono); color: var(--text-3); margin-top: 6px; }
nav { display: grid; gap: 2px; font-size: 14px; }
nav a { text-decoration: none; color: var(--text-2); padding: 3px 0; }
nav a:hover { color: var(--text); }
nav a.on { color: var(--text); font-weight: 600; }
nav a.on::before { content: "▸ "; color: var(--signal); }
h4 { font: 600 11px var(--font-mono); letter-spacing: .14em; color: var(--text-3); margin: 0 0 8px; }
.cur { display: grid; gap: 10px; }
.cur h4 { margin: 0; }
.rmeta { font-size: 13px; color: var(--text-2); min-width: 0; }
.rmeta b { display: block; font: 700 16px/1.3 var(--font-serif); color: var(--text); margin-bottom: 4px; overflow-wrap: anywhere; }
.rmeta div { font: 12px/1.8 var(--font-mono); color: var(--text-3); overflow-wrap: anywhere; }
.rsteps { list-style: none; margin: 0; padding: 0; position: relative; }
.rsteps::before { content: ""; position: absolute; left: 9px; top: 8px; bottom: 8px; width: 1px; background: var(--border-strong); }
.rsteps li { position: relative; display: grid; grid-template-columns: 20px 26px 1fr; align-items: baseline; padding: 4px 0; font-size: 14px; color: var(--text-3); }
.rsteps .dot { width: 9px; height: 9px; border: 1px solid var(--text-3); background: var(--surface-2); border-radius: 50%; margin: 0 0 0 5px; transform: translateY(1px); }
.rsteps .no { font: 11px var(--font-mono); }
.rsteps li.done { color: var(--text-2); }
.rsteps li.done .dot { background: var(--text-2); border-color: var(--text-2); }
.rsteps li.now { color: var(--text); font-weight: 600; }
.rsteps li.now .dot { background: var(--signal); border-color: var(--signal); box-shadow: 0 0 0 3px var(--surface-2), 0 0 0 4px var(--signal); }
.rfoot { margin-top: auto; display: grid; gap: 12px; }
.keys span { display: inline-flex; align-items: center; gap: 3px; }
.themebtn { justify-self: start; font: 12px var(--font-mono); background: none; border: 1px solid var(--border-strong); color: var(--text-2); padding: 3px 8px; cursor: pointer; }
.themebtn:hover { color: var(--text); border-color: var(--ink); }

.product-line { display: flex; align-items: baseline; gap: var(--sp-2); }
.product-line b { flex: 1; min-width: 0; }
.rsteps .prep-label { grid-column: 2 / -1; }
.rsteps a { color: var(--text-2); text-decoration: none; }
.rsteps .now a { color: var(--text); }
.rsteps a:hover { color: var(--text); text-decoration: underline; }
.extra-links { gap: 0; }
.extra-links a { position: relative; padding: 4px 0 4px 46px; }
.extra-links a.on::before { position: absolute; left: 28px; }
.shell-popover { width: min(440px, calc(100vw - 32px)); max-height: calc(100vh - 48px); overflow-y: auto; box-sizing: border-box; padding: var(--sp-5); border: 1px solid var(--border-strong); background: var(--surface); color: var(--text); box-shadow: var(--shadow-2); }
.shell-popover::backdrop { background: color-mix(in srgb, var(--bg) 65%, transparent); }
.popover-head { display: flex; align-items: center; justify-content: space-between; gap: var(--sp-3); margin-bottom: var(--sp-4); }
.popover-head h2 { font-size: var(--fs-lg); margin: 0; }
.shell-popover .keys { display: grid; gap: var(--sp-3); font-size: var(--fs-sm); color: var(--text-2); }
.details { margin: 0; font-size: var(--fs-sm); }
.details dt { color: var(--text-3); font-size: var(--fs-xs); margin-top: var(--sp-3); }
.details dd { margin: 4px 0 0; overflow-wrap: anywhere; }
.usage { white-space: pre-line; line-height: 1.8; }

@media (max-width: 1100px) {
  .rail { position: static; height: auto; flex-direction: row; flex-wrap: wrap; align-items: center; gap: 12px 24px; border-right: 0; border-bottom: 1px solid var(--ink); padding: 14px 20px; }
  .rail::after, h4, .motto, .rsteps.readonly { display: none; }
  nav { display: flex; flex-wrap: wrap; gap: 16px; }
  .cur { flex: 1; }
  .rmeta b { font-size: 14px; }
  .rflow { width: 100%; order: 3; display: flex; flex-wrap: wrap; gap: 16px; align-items: center; }
  .rsteps { display: flex; flex-wrap: wrap; gap: 16px; }
  .rsteps::before, .rsteps .dot, .rsteps .no, .rsteps li:not(:has(a)) { display: none; }
  .rsteps li { display: block; padding: 0; }
  .extra-links { gap: 16px; }
  .extra-links a { padding: 0; }
  .extra-links a.on::before { position: static; }
  .rfoot { margin: 0 0 0 auto; display: flex; flex-wrap: wrap; }
}
</style>
