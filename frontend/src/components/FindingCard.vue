<script setup>
import { computed, ref, inject } from 'vue'
import { F, P, evLabel } from '../lib/sim.js'
import { openDrawer } from '../lib/store.js'
import SevTag from './SevTag.vue'
import PersonaChip from './PersonaChip.vue'
import Avatar from './Avatar.vue'
import { Play, Image, Check, Terminal, Network } from 'lucide-vue-next'

const props = defineProps({ f: Object, rank: Number, active: Boolean })
const inDrawer = inject('inDrawer', false)
const hl = computed(() => props.f.kind === 'highlight')
const noEv = computed(() => props.f.evidence.length === 0)
const open = ref(!noEv.value)
const shown = computed(() => props.f.affected.slice(0, 3))
const color = computed(() => (hl.value ? 'var(--pos)' : `var(--sev-${props.f.sev})`))
// 严重度刻度：S1 满格（4），S4 一格
const level = computed(() => (hl.value ? 0 : 5 - props.f.sev))
const pct = computed(() => (props.f.denominator ? Math.round((props.f.affected.length / props.f.denominator) * 100) : 0))

// 证据按（人物，步骤）成组：同一步的步骤、录像、截图放在一起，一眼看出是谁的哪一步
const groups = computed(() => {
  const out = []
  const at = new Map()
  for (const ev of props.f.evidence) {
    const key = `${ev.pid}#${ev.step}`
    if (!at.has(key)) { at.set(key, out.length); out.push({ key, pid: ev.pid, step: ev.step, items: [] }) }
    out[at.get(key)].items.push(ev)
  }
  return out
})
const ICON = { video: Play, shots: Image, console: Terminal, network: Network }
function short(ev) {
  if (ev.kind === 'step') return `#${ev.step}`
  if (ev.kind === 'video') return evLabel(ev).replace(/^录像\s*/, '')
  if (ev.kind === 'shots') return `${ev.count || 1}`
  return evLabel(ev).replace(/\s*·\s*#\d+$/, '')
}
function openEv(ev) { openDrawer({ type: 'evidence', ev }, { fromDrawer: inDrawer }) }
function detail() { openDrawer({ type: 'finding', id: props.f.id }, { fromDrawer: inDrawer }) }
</script>

<template>
  <article class="finding" :class="{ active, noev: noEv, hl }" :style="{ '--fc': color }" :id="f.id">
    <div class="rail" aria-hidden="true">
      <span v-if="rank" class="rank num">{{ String(rank).padStart(2, '0') }}</span>
      <span v-if="hl" class="hlmark"><Check /></span>
      <span v-else class="meter" :title="`严重度 S${f.sev}`"><i v-for="n in 4" :key="n" :class="{ on: 5 - n <= level }"></i></span>
    </div>

    <div class="body">
      <div class="head">
        <SevTag :sev="f.sev" :highlight="hl" />
        <span class="tag">{{ f.flow ? F[f.flow].name : '跨流程' }}</span>
        <span v-if="noEv" class="tag noev">无证据</span>
        <span class="sp"></span>
        <span class="fid num">{{ f.id }}</span>
      </div>
      <h4><button type="button" class="title" @click="detail">{{ f.title }}</button></h4>
      <button v-if="noEv && !open" type="button" class="btn btn-ghost sm" @click="open = true">展开无证据的记录</button>

      <template v-if="open">
        <p class="why">{{ f.summary }}</p>

        <div class="facts">
          <div class="fact impact">
            <span class="k">影响</span>
            <span class="bar" :aria-label="`${f.affected.length}/${f.denominator}`">
              <i v-for="i in f.denominator" :key="i" :class="{ on: i <= f.affected.length }"></i>
            </span>
            <span class="num v">{{ f.affected.length }}<small>/{{ f.denominator }}</small></span>
            <span class="num pct faint">{{ pct }}%</span>
          </div>
          <div class="fact people">
            <span class="k">人物</span>
            <PersonaChip v-for="pid in shown" :key="pid" :pid="pid" />
            <button v-if="f.affected.length > 3" type="button" class="more" @click="detail">+{{ f.affected.length - 3 }}</button>
          </div>
          <p v-if="f.unfinished?.length" class="unfinished faint" title="报告只记录了这些人最终的结果，没有判断是否由这个问题导致">其中 {{ f.unfinished.length }} 人最终未完成体验</p>
        </div>

        <div v-if="!noEv" class="evs">
          <span class="k">证据</span>
          <div class="evlist">
            <span v-for="g in groups" :key="g.key" class="evg" :title="`${P[g.pid]?.realname ?? g.pid} · 第 ${g.step} 步`">
              <Avatar :pid="g.pid" size="sm" />
              <button v-for="(ev, i) in g.items" :key="i" type="button" class="seg-ev num" :class="ev.kind" :aria-label="evLabel(ev)" @click.stop="openEv(ev)">
                <component :is="ICON[ev.kind]" v-if="ICON[ev.kind]" />{{ short(ev) }}
              </button>
            </span>
          </div>
        </div>
      </template>
    </div>
  </article>
</template>

<style scoped>
.finding {
  --fc: var(--sev-1);
  position: relative; display: grid; grid-template-columns: 56px minmax(0, 1fr);
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg);
  box-shadow: var(--shadow-1), var(--edge); scroll-margin-top: 80px; overflow: hidden;
  transition: box-shadow var(--dur) var(--ease), border-color var(--dur) var(--ease), transform var(--dur) var(--ease);
}
.finding:hover { border-color: var(--border-strong); box-shadow: var(--shadow-hover), var(--edge); }
.finding.active { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-ring), var(--shadow-hover); }
.finding.noev { opacity: .8; }

.rail { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 22px 0 18px; border-right: 1px solid var(--border);
  background: linear-gradient(180deg, color-mix(in srgb, var(--fc) 7%, transparent), transparent 70%); }
.rank { font-size: 13px; font-weight: 600; color: var(--text-2); letter-spacing: -.02em; }
.meter { display: flex; flex-direction: column; gap: 3px; }
.meter i { width: 14px; height: 4px; border-radius: 2px; background: var(--surface-3); display: block; }
.meter i.on { background: var(--fc); box-shadow: 0 0 8px -1px color-mix(in srgb, var(--fc) 60%, transparent); }
.hlmark { width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; background: color-mix(in srgb, var(--pos) 14%, transparent); color: var(--pos); }
.hlmark svg { width: 13px; height: 13px; stroke-width: 2.5; }

.body { padding: 20px 24px 20px 22px; min-width: 0; }
.head { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.sp { flex: 1; }
.fid { font-size: 11px; color: var(--text-3); border: 1px solid var(--border); border-radius: 5px; padding: 0 6px; line-height: 20px; }
h4 { margin: 12px 0 6px; font-size: 17px; line-height: 1.45; letter-spacing: -.015em; }
.title { background: none; border: none; padding: 0; text-align: left; font: inherit; font-weight: 650; color: var(--text); cursor: pointer; }
.title:hover { color: var(--accent); }
.why { color: var(--text-2); font-size: var(--fs-sm); line-height: 1.7; margin: 0 0 16px; max-width: 780px; }

.k { width: 30px; flex: none; font-size: 11px; color: var(--text-3); font-weight: 600; letter-spacing: .04em; }
.facts { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 28px; padding: 12px 0; border-top: 1px dashed var(--border); }
.fact { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.bar { display: inline-flex; gap: 2px; }
.bar i { width: 10px; height: 14px; border-radius: 2px; background: var(--surface-3); display: block; }
.bar i.on { background: var(--fc); }
.v { font-size: var(--fs-sm); font-weight: 600; color: var(--text); }
.v small { color: var(--text-3); font-weight: 400; }
.pct { font-size: 11px; }
.more { height: 26px; padding: 0 9px; border-radius: var(--r-full); border: 1px dashed var(--border-strong); background: none; color: var(--text-2); cursor: pointer; font-size: var(--fs-xs); font-weight: 600; }
.more:hover { color: var(--accent); border-color: var(--accent); }
.unfinished { flex-basis: 100%; margin: 0; font-size: var(--fs-xs); padding-left: 38px; }

.evs { display: flex; align-items: flex-start; gap: 8px; padding-top: 12px; border-top: 1px dashed var(--border); }
.evs .k { line-height: 26px; }
.evlist { display: flex; flex-wrap: wrap; gap: 6px; min-width: 0; }
.evg { display: inline-flex; align-items: center; gap: 1px; height: 28px; padding: 0 2px 0 4px; border-radius: 8px; background: var(--surface-2); border: 1px solid var(--border); }
.evg .avatar { margin-right: 3px; }
.seg-ev { display: inline-flex; align-items: center; gap: 4px; height: 22px; padding: 0 7px; border: none; border-radius: 6px; background: none; color: var(--text-2); font-size: 11.5px; cursor: pointer; white-space: nowrap; transition: background var(--dur-fast) var(--ease), color var(--dur-fast) var(--ease); }
.seg-ev + .seg-ev { box-shadow: -1px 0 0 var(--border); border-radius: 0 6px 6px 0; }
.seg-ev svg { width: 11px; height: 11px; stroke-width: 2; }
.seg-ev.step { color: var(--text); font-weight: 600; }
.seg-ev:hover { background: var(--surface); color: var(--accent); box-shadow: 0 0 0 1px var(--border); }

@media (max-width: 640px) {
  .finding { grid-template-columns: 40px minmax(0, 1fr); }
  .body { padding: 16px; }
  .facts { gap: 10px 16px; }
}
</style>
