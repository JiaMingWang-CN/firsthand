<script setup>
import { computed, ref, inject } from 'vue'
import { F } from '../lib/sim.js'
import { openDrawer } from '../lib/store.js'
import SevTag from './SevTag.vue'
import EvTag from './EvTag.vue'
import PersonaChip from './PersonaChip.vue'
import DotMatrix from './DotMatrix.vue'

const props = defineProps({ f: Object, rank: Number, active: Boolean })
const inDrawer = inject('inDrawer', false)
const hl = computed(() => props.f.kind === 'highlight')
const noEv = computed(() => props.f.evidence.length === 0)
const open = ref(!noEv.value)
const shown = computed(() => props.f.affected.slice(0, 3))
const color = computed(() => (hl.value ? 'var(--pos)' : `var(--sev-${props.f.sev})`))
function detail() { openDrawer({ type: 'finding', id: props.f.id }, { fromDrawer: inDrawer }) }
</script>

<template>
  <article class="panel finding" :class="{ active, noev: noEv }" :style="{ borderLeftColor: color }" :id="f.id">
    <div class="head">
      <span v-if="rank" class="rank num">{{ String(rank).padStart(2, '0') }}</span>
      <SevTag :sev="f.sev" :highlight="hl" />
      <span v-if="f.flow" class="tag">{{ F[f.flow].name }}</span>
      <span v-else class="tag">跨流程</span>
      <span v-if="noEv" class="tag noev">无证据</span>
      <span class="sp"></span>
      <span class="fid num">{{ f.id }}</span>
    </div>
    <h4><button type="button" class="title" @click="detail">{{ f.title }}</button></h4>
    <button v-if="noEv && !open" type="button" class="btn btn-ghost sm" @click="open = true">展开无证据的记录</button>
    <template v-if="open">
      <p class="why">{{ f.summary }}</p>
      <div class="frow">
        <span class="k">影响</span>
        <DotMatrix :x="f.affected.length" :y="f.denominator" :color="color" />
        <span v-if="f.quit?.length" class="faint">其中 {{ f.quit.length }} 人放弃</span>
      </div>
      <div class="frow">
        <span class="k">人物</span>
        <PersonaChip v-for="pid in shown" :key="pid" :pid="pid" />
        <button v-if="f.affected.length > 3" type="button" class="more" @click="detail">+{{ f.affected.length - 3 }}</button>
      </div>
      <div class="frow" v-if="!noEv">
        <span class="k">证据</span>
        <EvTag v-for="(ev, i) in f.evidence" :key="i" :ev="ev" />
      </div>
    </template>
  </article>
</template>

<style scoped>
.finding { border-left: 3px solid var(--sev-1); transition: box-shadow var(--dur-fast) var(--ease), border-color var(--dur-fast) var(--ease); scroll-margin-top: 80px; }
.finding:hover { box-shadow: var(--shadow-1); }
.finding.active { box-shadow: 0 0 0 2px var(--accent); }
.finding.noev { opacity: .85; }
.head { display: flex; align-items: center; gap: var(--sp-2); flex-wrap: wrap; }
.rank { font-size: var(--fs-xs); color: var(--text-3); }
.sp { flex: 1; }
.fid { font-size: var(--fs-xs); color: var(--text-3); }
h4 { margin: var(--sp-2) 0 var(--sp-1); font-size: var(--fs-lg); line-height: 1.5; }
.title { background: none; border: none; padding: 0; text-align: left; font: inherit; font-weight: 700; color: var(--text); cursor: pointer; }
.title:hover { text-decoration: underline; text-decoration-color: var(--border-strong); text-underline-offset: 3px; }
.why { color: var(--text-2); font-size: var(--fs-sm); margin: 0 0 var(--sp-3); max-width: 760px; }
.frow { display: flex; align-items: center; gap: var(--sp-2); flex-wrap: wrap; font-size: var(--fs-xs); color: var(--text-3); }
.frow + .frow { margin-top: var(--sp-2); }
.k { width: 28px; flex: none; }
.more { background: none; border: none; color: var(--accent); cursor: pointer; font-size: var(--fs-xs); font-weight: 600; }
</style>
