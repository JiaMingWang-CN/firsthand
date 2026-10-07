<script setup>
// 一次运行从资料到报告的完整顺序。新建、审核、任务页都显示它：做到哪一步、哪些已完成、接下来该做什么。
import { Check, X, Loader } from 'lucide-vue-next'

const props = defineProps({
  at: { type: Number, required: true }, // 当前步骤（从 0 起，下标对应 STEPS）
  state: { type: String, default: 'active' }, // active 等你操作 | running 后台进行中 | failed 没有完成 | done 全部完成
})
const STEPS = ['填写资料', '分析资料', '确认人数与天数', '生成人物', '审核批准', '模拟体验与讨论', '生成报告']
const TAG = { active: '等你操作', running: '后台进行中，不需要操作', failed: '没有完成' }
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
.flow { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg); padding: var(--sp-4) var(--sp-5); margin-bottom: var(--sp-4); box-shadow: var(--shadow-1), var(--edge); }
.track { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); }
.track li { position: relative; display: flex; flex-direction: column; align-items: center; gap: 6px; text-align: center; font-size: var(--fs-xs); color: var(--text-3); }
.track li + li::before { content: ''; position: absolute; top: 11px; left: calc(-50% + 16px); right: calc(50% + 16px); height: 2px; border-radius: 1px; background: var(--border); }
.track li.done + li::before { background: var(--pos); }
.mark { width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center; border: 1.5px solid var(--border-strong); background: var(--surface); font-weight: 600; }
.mark svg { width: 14px; height: 14px; stroke-width: 2.25; }
.done { color: var(--text-2); }
.done .mark { background: var(--pos); border-color: var(--pos); color: var(--surface); }
.active, .running, .failed { color: var(--text); font-weight: 600; }
.active .mark { background: var(--accent); border-color: var(--accent); color: var(--on-accent); box-shadow: 0 0 0 4px var(--accent-ring); }
.running .mark { border-color: var(--sim); color: var(--sim); background: var(--sim-soft); }
.failed .mark { background: var(--neg); border-color: var(--neg); color: var(--surface); }
.next { display: flex; align-items: center; gap: var(--sp-2) var(--sp-3); flex-wrap: wrap; margin-top: var(--sp-4); padding-top: var(--sp-3); border-top: 1px solid var(--border); font-size: var(--fs-sm); }
.where { font-weight: 600; }
.next.active .where { color: var(--accent); }
.next.running .where { color: var(--sim); }
.next.failed .where { color: var(--neg); }
.next.done .where { color: var(--pos); }
.say { color: var(--text-2); flex: 1 1 280px; line-height: 1.6; }
.act { display: flex; gap: var(--sp-2); margin-left: auto; }
.act:empty { display: none; }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 959px) {
  .track { display: flex; flex-wrap: wrap; gap: var(--sp-2) var(--sp-3); }
  .track li { flex-direction: row; }
  .track li + li::before { display: none; }
  .track li.todo .name { display: none; }
}
</style>
