<script setup>
// 一次运行从资料到报告的完整顺序。新建、审核、任务页都显示它：做到哪一步、哪些已完成、接下来该做什么。
import { watchEffect, onBeforeUnmount } from 'vue'
import { Check, X, Loader } from 'lucide-vue-next'
import { flowState } from '../lib/shell.js'

const props = defineProps({
  at: { type: Number, required: true }, // 当前步骤（从 0 起，下标对应 STEPS）
  state: { type: String, default: 'active' }, // active 等你操作 | running 后台进行中 | failed 没有完成 | done 全部完成
})
const STEPS = ['填写资料', '分析资料', '确认人数与天数', '生成人物', '审核批准', '模拟体验与讨论', '生成报告']
const TAG = { active: '等你操作', running: '后台进行中，不需要操作', failed: '没有完成' }
// 侧栏的流程列表跟着这里走
watchEffect(() => {
  flowState.done = props.state === 'done'
  flowState.at = flowState.done ? STEPS.length - 1 : props.at
})
onBeforeUnmount(() => { flowState.at = null; flowState.done = false })
const of = (i) => (props.state === 'done' || i < props.at ? 'done' : i === props.at ? props.state : 'todo')
</script>

<template>
  <section class="flow" aria-label="运行流程">
    <ol class="track">
      <li v-for="(s, i) in STEPS" :key="s" :class="of(i)" :aria-current="i === at && state !== 'done' ? 'step' : undefined">
        <span class="mark num">
          <Check v-if="of(i) === 'done'" /><X v-else-if="of(i) === 'failed'" /><Loader v-else-if="of(i) === 'running'" class="spin" /><template v-else>{{ i + 1 }}</template>
        </span>
        <span class="name">{{ s }}</span>
      </li>
    </ol>
    <div class="next" :class="state">
      <span class="where">{{ state === 'done' ? '全部完成' : `第 ${at + 1}/${STEPS.length} 步 · ${STEPS[at]} · ${TAG[state]}` }}</span>
      <span class="say"><slot /></span>
      <span class="act"><slot name="action" /></span>
    </div>
  </section>
</template>

<style scoped>
/* 页内只留两样：窄屏时侧栏收起，用一行文字顶替流程；“现在该做什么”始终显示 */
.flow { margin-bottom: var(--sp-4); }
.track { list-style: none; margin: 0 0 var(--sp-3); padding: 0; display: none; flex-wrap: wrap; gap: 4px 0; font-size: var(--fs-sm); color: var(--text-3); }
.track li { display: inline-flex; align-items: center; gap: 6px; }
.track li:not(:last-child)::after { content: "→"; margin: 0 8px; color: var(--border-strong); }
.mark { display: inline-flex; font-size: 11px; }
.mark svg { width: 12px; height: 12px; stroke-width: 2.25; }
.done { color: var(--text-2); }
.active, .running, .failed { color: var(--text); font-weight: 600; }
.failed { color: var(--neg); }
.next { display: flex; align-items: center; gap: var(--sp-2) var(--sp-3); flex-wrap: wrap; padding: 4px 0 4px 14px; border-left: 3px solid var(--confused); font-size: var(--fs-sm); }
.next.running { border-left-color: var(--sim); }
.next.failed { border-left-color: var(--signal); }
.next.done { border-left-color: var(--pos); }
.where { font-weight: 600; }
.next.failed .where { color: var(--neg); }
.next.done .where { color: var(--pos); }
.say { color: var(--text-2); flex: 1 1 280px; line-height: 1.6; }
.act { display: flex; gap: var(--sp-2); margin-left: auto; }
.act:empty { display: none; }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 1100px) {
  .track { display: flex; }
  .track li.todo .mark { display: none; }
}
</style>
