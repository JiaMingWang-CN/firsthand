<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { product, live, personas, timeline, run } from '../lib/data.js'
import { ui, toggleTheme } from '../lib/store.js'
import { STEPS, flowState, ROUTE_STEP } from '../lib/shell.js'

const route = useRoute()
const runId = computed(() => route.params.runId)
const runLinks = [
  { name: 'report', label: '报告' },
  { name: 'live', label: '运行现场' },
  { name: 'personas', label: '人物' },
  { name: 'community', label: '社区' },
  { name: 'interview', label: '采访' },
]
const keepQuery = (name) => (['live', 'community'].includes(name) && route.query.t ? { t: route.query.t } : {})
const ready = computed(() => live.id === runId.value && product.name)
// 当前在流程的哪一步：带流程条的页面以它为准，其余页面按路由固定对应
const at = computed(() => flowState.at ?? ROUTE_STEP[route.name] ?? null)
const stepClass = (i) => (at.value == null ? '' : i < at.value || (flowState.done && i === at.value) ? 'done' : i === at.value ? 'now' : '')
const meta = computed(() => [
  `${personas.length} 人 · ${Math.max(1, Math.round(timeline.total / 1440))} 天 · 每格 ${timeline.sliceMinutes} 分钟`,
  run.usage?.models?.[0]?.model,
].filter(Boolean))
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
      <div class="rmeta" :title="runId">
        <b>{{ ready ? product.name : '加载中…' }}</b>
        <div class="num">{{ runId }}</div>
        <template v-if="ready"><div v-for="m in meta" :key="m">{{ m }}</div></template>
      </div>
      <nav aria-label="当前运行">
        <RouterLink v-for="l in runLinks" :key="l.name" :to="{ name: l.name, params: { runId }, query: keepQuery(l.name) }"
                    :class="{ on: route.name === l.name }">{{ l.label }}</RouterLink>
      </nav>
    </div>

    <div>
      <h4>流程</h4>
      <ol class="rsteps">
        <li v-for="(s, i) in STEPS" :key="s" :class="stepClass(i)" :aria-current="i === at && !flowState.done ? 'step' : undefined">
          <span class="dot"></span><span class="no">{{ String(i + 1).padStart(2, '0') }}</span><span>{{ s }}</span>
        </li>
      </ol>
    </div>

    <div class="rfoot">
      <div class="keys"><span><kbd>Esc</kbd> 关闭</span><span><kbd>J</kbd><kbd>K</kbd> 切换</span><span><kbd>/</kbd> 搜索</span><span><kbd>空格</kbd> 播放</span></div>
      <button type="button" class="themebtn" @click="toggleTheme" :aria-label="ui.theme === 'dark' ? '切换到浅色主题' : '切换到深色主题'">{{ ui.theme === 'dark' ? '切换到浅色' : '切换到深色' }}</button>
    </div>
  </aside>
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
.keys { display: flex; flex-wrap: wrap; gap: 4px 10px; font-size: 11px; color: var(--text-3); }
.keys span { display: inline-flex; align-items: center; gap: 3px; }
.themebtn { justify-self: start; font: 12px var(--font-mono); background: none; border: 1px solid var(--border-strong); color: var(--text-2); padding: 3px 8px; cursor: pointer; }
.themebtn:hover { color: var(--text); border-color: var(--ink); }

@media (max-width: 1100px) {
  .rail { position: static; height: auto; flex-direction: row; flex-wrap: wrap; align-items: center; gap: 12px 24px; border-right: 0; border-bottom: 1px solid var(--ink); padding: 14px 20px; }
  .rail::after, h4, .rsteps, .rmeta, .keys, .motto { display: none; }
  nav { display: flex; gap: 16px; }
  .cur { display: flex; gap: 16px; align-items: center; }
  .rfoot { margin: 0 0 0 auto; }
}
</style>
