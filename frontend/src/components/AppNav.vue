<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { product, live } from '../lib/data.js'
import { ui, toggleTheme } from '../lib/store.js'
import { History, Plus, FileText, Radio, Users, MessagesSquare, Mic, Sun, Moon } from 'lucide-vue-next'

const route = useRoute()
const runId = computed(() => route.params.runId)
const runLinks = [
  { name: 'report', label: '报告', icon: FileText },
  { name: 'live', label: '运行现场', icon: Radio },
  { name: 'personas', label: '人物', icon: Users },
  { name: 'community', label: '社区', icon: MessagesSquare },
  { name: 'interview', label: '采访', icon: Mic },
]
const keepQuery = (name) => (['live', 'community'].includes(name) && route.query.t ? { t: route.query.t } : {})
const ready = computed(() => live.id === runId.value && product.name)
</script>

<template>
  <nav class="nav" aria-label="主导航">
    <RouterLink to="/runs" class="brand" aria-label="muchhuman 首页">
      <span class="logo" aria-hidden="true"><i></i><i></i></span>
      <span class="bt"><b>muchhuman</b><small>模拟人物 · 真实体验</small></span>
    </RouterLink>

    <div class="grp">
      <div class="gl">工作台</div>
      <RouterLink to="/runs" class="it" :class="{ on: route.name === 'runs' }"><History /><span>运行</span></RouterLink>
      <RouterLink to="/new" class="it" :class="{ on: route.name === 'new' }"><Plus /><span>新建运行</span></RouterLink>
    </div>

    <div class="grp" v-if="route.params.runId">
      <div class="gl">当前运行</div>
      <div class="cur" :title="runId">
        <span class="ct">{{ ready ? product.name : '加载中…' }}</span>
        <span class="cs num">{{ runId }}</span>
      </div>
      <RouterLink v-for="l in runLinks" :key="l.name" :to="{ name: l.name, params: { runId }, query: keepQuery(l.name) }"
                  class="it" :class="{ on: route.name === l.name }"><component :is="l.icon" /><span>{{ l.label }}</span></RouterLink>
    </div>

    <div class="foot">
      <div class="demo"><span class="dot"></span><span>真实运行数据</span></div>
      <button class="it themebtn" type="button" @click="toggleTheme" :aria-label="ui.theme === 'dark' ? '切换到浅色主题' : '切换到深色主题'">
        <component :is="ui.theme === 'dark' ? Sun : Moon" /><span>{{ ui.theme === 'dark' ? '浅色主题' : '深色主题' }}</span>
      </button>
      <div class="keys"><span><kbd>Esc</kbd> 关闭</span><span><kbd>J</kbd><kbd>K</kbd> 切换</span><span><kbd>/</kbd> 搜索</span><span><kbd>空格</kbd> 播放</span></div>
    </div>
  </nav>
</template>

<style scoped>
.nav { position: sticky; top: 0; height: 100vh; display: flex; flex-direction: column; gap: var(--sp-5); padding: var(--sp-5) var(--sp-3) var(--sp-4); border-right: 1px solid var(--border); background: color-mix(in srgb, var(--surface) 55%, var(--bg)); overflow-y: auto; }
.brand { display: flex; align-items: center; gap: 11px; padding: 2px var(--sp-2); color: var(--text); text-decoration: none !important; }
.logo { width: 30px; height: 30px; border-radius: 9px; background: linear-gradient(135deg, var(--brand-a), var(--brand-b)); display: grid; grid-template-columns: 1fr 1fr; align-items: center; justify-items: center; padding: 0 5px; flex: none; box-shadow: inset 0 1px 0 rgba(255,255,255,.3), 0 4px 14px -4px color-mix(in srgb, var(--brand-a) 60%, transparent); }
.logo i { width: 8px; height: 8px; border-radius: 50%; background: #fff; display: block; }
.logo i + i { background: transparent; border: 1.5px dashed #fff; }
.bt { display: flex; flex-direction: column; line-height: 1.25; }
.bt b { font-size: 15px; font-weight: 700; letter-spacing: -.025em; }
.bt small { font-size: 11px; color: var(--text-3); margin-top: 1px; }
.grp { display: flex; flex-direction: column; gap: 1px; }
.gl { font-size: 10.5px; font-weight: 600; letter-spacing: .1em; text-transform: uppercase; color: var(--text-3); padding: 0 var(--sp-2) 6px; }
.it { position: relative; display: flex; align-items: center; gap: 10px; height: 34px; padding: 0 10px; border-radius: 8px; color: var(--text-2); font-size: var(--fs-sm); font-weight: 550; text-decoration: none !important; border: none; background: none; cursor: pointer; width: 100%; text-align: left; transition: background var(--dur-fast) var(--ease), color var(--dur-fast) var(--ease), box-shadow var(--dur-fast) var(--ease); }
.it svg { width: 16px; height: 16px; stroke-width: 1.75; flex: none; color: var(--text-3); transition: color var(--dur-fast) var(--ease); }
.it:hover { background: color-mix(in srgb, var(--surface-3) 70%, transparent); color: var(--text); }
.it:hover svg { color: var(--text-2); }
.it.on { background: var(--surface); color: var(--text); font-weight: 600; box-shadow: 0 1px 2px rgba(13,16,21,.06), 0 0 0 1px var(--border); }
.it.on svg { color: var(--accent); }
.it.on::before { content: ""; position: absolute; left: -12px; top: 9px; bottom: 9px; width: 3px; border-radius: 0 3px 3px 0; background: linear-gradient(var(--brand-a), var(--brand-b)); }
.cur { margin: 0 0 6px; padding: 10px 12px; display: flex; flex-direction: column; gap: 2px; border-radius: 10px; border: 1px dashed var(--border-strong); min-width: 0; }
.ct { font-size: var(--fs-sm); font-weight: 600; line-height: 1.4; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cs { font-size: 10.5px; color: var(--text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.foot { margin-top: auto; display: flex; flex-direction: column; gap: 4px; padding-top: var(--sp-3); border-top: 1px solid var(--border); }
.demo { display: flex; align-items: center; gap: var(--sp-2); font-size: var(--fs-xs); color: var(--text-3); padding: 4px 10px; }
.demo .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--pos); box-shadow: 0 0 0 3px var(--pos-soft); }
.keys { display: flex; flex-wrap: wrap; gap: 4px 10px; font-size: 11px; color: var(--text-3); padding: 6px 10px 0; }
.keys span { display: inline-flex; align-items: center; gap: 3px; }

@media (max-width: 1279px) and (min-width: 960px) {
  .nav { padding: var(--sp-5) var(--sp-2); align-items: center; }
  .bt, .gl, .cur, .demo, .keys, .it span { display: none; }
  .it { width: 40px; justify-content: center; padding: 0; }
  .it.on::before { left: -8px; }
  .brand { padding: 0; }
  .foot { border-top: none; }
}
@media (max-width: 959px) {
  .nav { position: sticky; top: 0; height: auto; flex-direction: row; align-items: center; gap: var(--sp-2); padding: var(--sp-2) var(--sp-4); border-right: none; border-bottom: 1px solid var(--border); overflow-x: auto; z-index: 30; background: color-mix(in srgb, var(--bg) 85%, transparent); backdrop-filter: blur(12px); }
  .bt small, .gl, .cur, .demo, .keys, .themebtn span { display: none; }
  .grp { flex-direction: row; }
  .grp:first-of-type { display: none; }
  .it { width: auto; white-space: nowrap; }
  .it.on::before { display: none; }
  .foot { margin: 0 0 0 auto; flex-direction: row; border-top: none; padding-top: 0; }
  .themebtn { width: 34px; justify-content: center; }
}
</style>
