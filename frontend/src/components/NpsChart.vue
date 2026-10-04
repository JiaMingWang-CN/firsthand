<script setup>
import { computed, ref } from 'vue'
import { surveys } from '../lib/data.js'
import { P, npsOf } from '../lib/sim.js'
import PersonaChip from './PersonaChip.vue'
import Avatar from './Avatar.vue'

const asTable = ref(false)
const cols = computed(() => Array.from({ length: 11 }, (_, n) => ({
  n, pids: Object.entries(surveys).filter(([, s]) => s.nps === n).map(([pid]) => pid),
})))
// 没有亲身体验的人物没有 NPS，不计入
const scored = computed(() => Object.values(surveys).map((s) => s.nps).filter(Number.isInteger))
const nps = computed(() => npsOf(scored.value))
const total = computed(() => scored.value.length)
</script>

<template>
  <div>
    <div class="head">
      <span class="label">离场问卷 · 推荐意愿（0–10）</span>
      <button class="btn btn-ghost sm" type="button" @click="asTable = !asTable">{{ asTable ? '查看图表' : '查看表格' }}</button>
    </div>
    <div v-if="!asTable" class="chart" role="img"
         :aria-label="`推荐意愿分布：贬损者 ${nps.detractors} 人，被动者 ${nps.passives} 人，推荐者 ${nps.promoters} 人，NPS ${nps.score}。`">
      <div class="zones">
        <div class="z" style="flex: 7">贬损 0–6 · {{ nps.detractors }}/{{ total }}</div>
        <div class="z" style="flex: 2" title="被动 7–8">被动 {{ nps.passives }}</div>
        <div class="z" style="flex: 2" title="推荐 9–10">推荐 {{ nps.promoters }}</div>
      </div>
      <div class="cols">
        <div v-for="c in cols" :key="c.n" class="col">
          <div class="stack">
            <span v-for="pid in c.pids" :key="pid" :title="`${P[pid].realname} · ${c.n} 分`"><Avatar :pid="pid" size="sm" /></span>
          </div>
          <div class="n num">{{ c.n }}</div>
        </div>
      </div>
    </div>
    <div v-else class="table-wrap tblw">
      <table class="data compact">
        <thead><tr><th>人物</th><th class="r">推荐意愿</th><th>继续使用</th><th>付费</th></tr></thead>
        <tbody>
          <tr v-for="(s, pid) in surveys" :key="pid"><td><PersonaChip :pid="pid" /></td><td class="r num">{{ s.nps ?? '—' }}</td><td>{{ s.keep }}</td><td>{{ s.pay }}</td></tr>
        </tbody>
      </table>
    </div>
    <div class="source">来源：离场问卷 · {{ total }}/{{ Object.keys(surveys).length }} 名人物有亲身体验并给出推荐意愿（含潜水者）</div>
  </div>
</template>

<style scoped>
.head { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--sp-2); }
.zones { display: flex; gap: 2px; margin-bottom: var(--sp-2); }
.z { background: var(--surface-2); font-size: var(--fs-xs); color: var(--text-2); padding: 2px 8px; border-radius: var(--r-sm); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cols { display: grid; grid-template-columns: repeat(11, 1fr); gap: 2px; border-bottom: 1px solid var(--border-strong); }
.col { display: flex; flex-direction: column; align-items: center; }
.stack { display: flex; flex-direction: column-reverse; gap: 3px; min-height: 104px; justify-content: flex-start; padding-bottom: 4px; }
.n { font-size: var(--fs-xs); color: var(--text-3); padding: 2px 0; }
.tblw { max-height: 280px; overflow: auto; border: 1px solid var(--border); border-radius: var(--r-md); }
</style>
