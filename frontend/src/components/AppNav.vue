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
      <div class="cur">
        <span class="ct">{{ live.id === runId && product.name ? product.name : '加载中…' }}</span>
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
      <div class="keys"><kbd>Esc</kbd> 关闭 <kbd>J</kbd><kbd>K</kbd> 切换 <kbd>/</kbd> 搜索 <kbd>空格</kbd> 播放</div>
    </div>
  </nav>
</template>

<style scoped>
.nav { position: sticky; top: 0; height: 100vh; display: flex; flex-direction: column; gap: var(--sp-5); padding: var(--sp-5) var(--sp-3); border-right: 1px solid var(--border); background: var(--bg); overflow-y: auto; }
.brand { display: flex; align-items: center; gap: var(--sp-3); padding: 0 var(--sp-2); color: var(--text); text-decoration: none !important; }
.logo { width: 32px; height: 32px; border-radius: var(--r-md); background: var(--text); display: grid; grid-template-columns: 1fr 1fr; align-items: center; justify-items: center; padding: 0 5px; flex: none; }
.logo i { width: 9px; height: 9px; border-radius: 50%; background: var(--bg); display: block; }
.logo i + i { background: transparent; border: 1.5px dashed var(--bg); }
.bt { display: flex; flex-direction: column; line-height: 1.3; }
.bt b { font-size: var(--fs-lg); letter-spacing: -.01em; }
.bt small { font-size: var(--fs-xs); color: var(--text-3); }
.grp { display: flex; flex-direction: column; gap: 2px; }
.gl { font-size: var(--fs-xs); color: var(--text-3); padding: 0 var(--sp-2) var(--sp-1); }
.it { display: flex; align-items: center; gap: var(--sp-3); height: 34px; padding: 0 var(--sp-2); border-radius: var(--r-md); color: var(--text-2); font-size: var(--fs-sm); font-weight: 600; text-decoration: none !important; border: none; background: none; cursor: pointer; width: 100%; text-align: left; transition: background var(--dur-fast) var(--ease), color var(--dur-fast) var(--ease); }
.it svg { width: 16px; height: 16px; stroke-width: 1.5; flex: none; }
.it:hover { background: var(--surface-2); color: var(--text); }
.it.on { background: var(--surface); color: var(--text); box-shadow: inset 0 0 0 1px var(--border); }
.it.on svg { color: var(--accent); }
.cur { padding: var(--sp-2); margin-bottom: var(--sp-1); display: flex; flex-direction: column; border-left: 2px solid var(--border-strong); margin-left: var(--sp-2); }
.ct { font-size: var(--fs-sm); font-weight: 600; }
.cs { font-size: var(--fs-xs); color: var(--text-3); }
.foot { margin-top: auto; display: flex; flex-direction: column; gap: var(--sp-2); }
.demo { display: flex; align-items: center; gap: var(--sp-2); font-size: var(--fs-xs); color: var(--text-3); padding: 0 var(--sp-2); }
.demo .dot { width: 6px; height: 6px; border-radius: 50%; border: 1.5px solid var(--text-3); }
.keys { font-size: var(--fs-xs); color: var(--text-3); padding: 0 var(--sp-2); line-height: 2; }

@media (max-width: 1279px) and (min-width: 960px) {
  .nav { padding: var(--sp-5) var(--sp-2); align-items: center; }
  .bt, .gl, .cur, .demo, .keys, .it span { display: none; }
  .it { width: 40px; justify-content: center; padding: 0; }
  .brand { padding: 0; }
}
@media (max-width: 959px) {
  .nav { position: sticky; top: 0; height: auto; flex-direction: row; align-items: center; gap: var(--sp-2); padding: var(--sp-2) var(--sp-4); border-right: none; border-bottom: 1px solid var(--border); overflow-x: auto; z-index: 30; }
  .bt small, .gl, .cur, .demo, .keys, .themebtn span { display: none; }
  .grp { flex-direction: row; }
  .grp:first-of-type { display: none; }
  .it { width: auto; white-space: nowrap; }
  .foot { margin: 0 0 0 auto; flex-direction: row; }
  .themebtn { width: 34px; justify-content: center; }
}
</style>
