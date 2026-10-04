<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { steps } from '../mock/data.js'
import { resolveEvidence, findingsCiting, fmt, mmss, label } from '../lib/sim.js'
import { openDrawer, toast } from '../lib/store.js'
import { Copy, Film, Terminal, Globe, EyeOff, Eye, ChevronLeft, ChevronRight, ExternalLink } from 'lucide-vue-next'
import PersonaChip from './PersonaChip.vue'
import SimTime from './SimTime.vue'
import MockScreen from './MockScreen.vue'
import SevTag from './SevTag.vue'

const props = defineProps({ ev: Object })
const stepNo = ref(props.ev.step)
const r = computed(() => resolveEvidence({ ...props.ev, step: stepNo.value }))
const p = computed(() => r.value.persona)
const st = computed(() => r.value.step)
const canSeeTrace = computed(() => p.value.tools.length > 0)
const citing = computed(() => findingsCiting(p.value.id, stepNo.value))
const total = computed(() => steps[p.value.id].length)
const mood = computed(() => {
  const s = st.value.sat
  if (st.value.conf >= .5) return { cls: 'confused', text: `困惑 ${st.value.conf.toFixed(1)}` }
  return s >= .3 ? { cls: 'pos', text: `满意 ${s.toFixed(1)}` } : s <= -.3 ? { cls: 'neg', text: `受挫 ${s.toFixed(1)}` } : { cls: '', text: `平稳 ${s.toFixed(1)}` }
})
const kindIcon = { video: Film, console: Terminal, network: Globe }
const focusKind = props.ev.kind

function go(d) { stepNo.value = Math.max(1, Math.min(total.value, stepNo.value + d)) }
function copyTrace() {
  const text = r.value.trace.map((t) => `[${t.type}] ${t.level} ${t.text}`).join('\n')
  navigator.clipboard?.writeText(text).catch(() => {})
  toast('已复制轨迹')
}
function onKey(e) {
  if (e.target.closest('input, textarea')) return
  if (e.key === 'j' || e.key === 'J') go(1)
  if (e.key === 'k' || e.key === 'K') go(-1)
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="evv">
    <!-- 必须同时显示：人物、模拟时间、步骤、URL、截图、观察权限 -->
    <div class="meta row">
      <PersonaChip :pid="p.id" />
      <SimTime :m="st.t" />
      <span class="stepno num">步骤 #{{ stepNo }}<span class="faint">/{{ total }}</span></span>
      <span class="sp"></span>
      <button class="btn btn-ghost icon sm" type="button" :disabled="stepNo <= 1" aria-label="上一步（K）" @click="go(-1)"><ChevronLeft /></button>
      <button class="btn btn-ghost icon sm" type="button" :disabled="stepNo >= total" aria-label="下一步（J）" @click="go(1)"><ChevronRight /></button>
    </div>
    <h3 class="act">{{ st.act }}</h3>
    <div class="url num">{{ st.path.startsWith('mail.') ? st.path : 'https://demo.qingtan.test' + st.path }}</div>

    <MockScreen class="shot" :screen="st.screen" :device="st.device || p.device" :target="st.target" :path="st.path" :time="fmt(st.t).slice(3)" />

    <div class="row tags">
      <span class="tag" :class="mood.cls"><span class="dot"></span>{{ mood.text }}</span>
      <span class="tag">{{ label.device[p.device] }} · {{ p.device === 'mobile' ? '390×844' : '1440×900' }}</span>
      <span class="tag">{{ p.timezone }}</span>
      <span class="perm" :class="{ ok: canSeeTrace }">
        <component :is="canSeeTrace ? Eye : EyeOff" />
        {{ canSeeTrace ? `该人物可以通过 ${p.tools.join('、')} 查看轨迹` : '该人物看不到 Console 和 Network' }}
      </span>
    </div>

    <div class="think" v-if="st.think">
      <div class="label">当时的想法 · 体验记录</div>
      <p>{{ st.think }}</p>
    </div>

    <!-- 录像片段 -->
    <section class="blk" :class="{ focus: focusKind === 'video' }">
      <div class="bh"><Film /><b>录像片段</b><span class="faint num">{{ mmss(Math.max(0, r.video - 5)) }} – {{ mmss(r.video + 5) }}</span><span class="sp"></span>
        <button class="btn btn-ghost sm" type="button" @click="toast('演示数据：真实版本会打开 Steel 录像并定位到 ' + mmss(r.video))"><ExternalLink />打开录像</button>
      </div>
      <div class="player">
        <div class="bar"><i :style="{ left: `${(r.video / (r.video + 120)) * 100}%` }"></i><span class="win" :style="{ left: `${((r.video - 5) / (r.video + 120)) * 100}%` }"></span></div>
        <div class="row faint pl"><span class="num">定位到 {{ mmss(r.video) }}，前后各留 5 秒</span></div>
      </div>
    </section>

    <!-- 轨迹 -->
    <section class="blk" :class="{ focus: focusKind === 'console' || focusKind === 'network' }">
      <div class="bh"><Terminal /><b>轨迹</b><span class="faint">Console · Network</span><span class="sp"></span>
        <button v-if="r.trace.length" class="btn btn-ghost sm" type="button" @click="copyTrace"><Copy />复制</button>
      </div>
      <div v-if="r.trace.length" class="trace">
        <div v-for="(t, i) in r.trace" :key="i" class="tl" :class="t.level">
          <span class="ty">{{ t.type === 'console' ? 'CON' : 'NET' }}</span>
          <span class="lv">{{ t.level }}</span>
          <span class="tx">{{ t.text }}</span>
        </div>
      </div>
      <p v-else class="faint empty">这一步没有错误或警告。旁路采集仍保存了完整轨迹。</p>
      <p v-if="r.trace.length && !canSeeTrace" class="faint empty">这些数据由旁路采集记录，人物本身在体验时看不到。</p>
    </section>

    <!-- 反向引用 -->
    <section class="blk">
      <div class="bh"><b>引用了这条证据的发现</b><span class="faint num">{{ citing.length }}</span></div>
      <div v-if="citing.length" class="cites">
        <button v-for="f in citing" :key="f.id" type="button" class="cite" @click="openDrawer({ type: 'finding', id: f.id }, { fromDrawer: true })">
          <SevTag :sev="f.sev" :highlight="f.kind === 'highlight'" /><span class="ct">{{ f.title }}</span><span class="num faint">{{ f.id }}</span>
        </button>
      </div>
      <p v-else class="faint empty">还没有发现引用这一步。</p>
    </section>

    <!-- 步骤条 -->
    <section class="blk">
      <div class="bh"><b>{{ p.realname }} 的全部步骤</b><span class="faint">{{ label.outcome[p.outcome] }}</span></div>
      <ol class="strip">
        <li v-for="(s, i) in steps[p.id]" :key="i">
          <button type="button" :class="{ cur: i + 1 === stepNo }" @click="stepNo = i + 1">
            <span class="num sn">#{{ i + 1 }}</span>
            <span class="moodbar" :style="{ background: s.sat >= .3 ? 'var(--pos)' : s.sat <= -.3 ? 'var(--neg)' : 'var(--border-strong)' }"></span>
            <span class="sa">{{ s.act }}</span>
            <span class="num faint">{{ fmt(s.t).slice(3) }}</span>
          </button>
        </li>
      </ol>
    </section>
  </div>
</template>

<style scoped>
.meta { gap: var(--sp-2); }
.stepno { font-size: var(--fs-xs); font-weight: 600; }
.sp { flex: 1; }
.act { font-size: var(--fs-lg); line-height: 1.5; margin: var(--sp-3) 0 2px; }
.url { font-size: var(--fs-xs); color: var(--text-3); word-break: break-all; margin-bottom: var(--sp-3); }
.shot { margin-bottom: var(--sp-3); }
.shot.m, :deep(.shot.m) { max-width: 260px; margin-left: auto; margin-right: auto; }
.tags { gap: 6px; margin-bottom: var(--sp-4); }
.perm { display: inline-flex; align-items: center; gap: 5px; font-size: var(--fs-xs); color: var(--text-2); background: var(--surface-2); border-radius: var(--r-sm); padding: 2px 8px; }
.perm svg { width: 14px; height: 14px; stroke-width: 1.5; }
.think { border-left: 2px solid var(--border-strong); padding-left: var(--sp-3); margin-bottom: var(--sp-4); }
.think p { margin: 2px 0 0; color: var(--text-2); font-size: var(--fs-sm); }
.blk { border-top: 1px solid var(--border); padding: var(--sp-4) 0; }
.blk.focus { background: linear-gradient(90deg, var(--accent-soft), transparent 70%); margin: 0 calc(-1 * var(--sp-5)); padding-left: var(--sp-5); padding-right: var(--sp-5); }
.bh { display: flex; align-items: center; gap: var(--sp-2); font-size: var(--fs-sm); margin-bottom: var(--sp-2); }
.bh svg { width: 16px; height: 16px; stroke-width: 1.5; color: var(--text-2); }
.bh .faint { font-size: var(--fs-xs); }
.player .bar { position: relative; height: 6px; border-radius: 3px; background: var(--surface-2); margin: var(--sp-2) 0; }
.player .bar i { position: absolute; top: -4px; width: 2px; height: 14px; background: var(--text); display: block; }
.player .win { position: absolute; top: 0; height: 6px; width: 8%; background: var(--border-strong); border-radius: 3px; }
.pl { font-size: var(--fs-xs); }
.trace { background: var(--surface-2); border-radius: var(--r-md); padding: var(--sp-2) var(--sp-3); font-family: var(--font-mono); font-size: var(--fs-xs); overflow-x: auto; }
.tl { display: flex; gap: var(--sp-2); padding: 3px 0; white-space: nowrap; }
.tl .ty { color: var(--text-3); }
.tl .lv { width: 40px; flex: none; }
.tl.error .lv, .tl.error .tx { color: var(--neg); }
.tl.warn .lv, .tl.warn .tx { color: var(--confused); }
.tl.info .lv { color: var(--text-3); }
.empty { font-size: var(--fs-xs); margin: 0; }
.cites { display: grid; gap: var(--sp-2); }
.cite { display: flex; align-items: center; gap: var(--sp-2); text-align: left; background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-md); padding: var(--sp-2) var(--sp-3); cursor: pointer; font-size: var(--fs-sm); }
.cite:hover { background: var(--surface-2); }
.ct { flex: 1; min-width: 0; }
.strip { list-style: none; padding: 0; margin: 0; display: grid; gap: 2px; }
.strip button { width: 100%; display: flex; align-items: center; gap: var(--sp-2); border: none; background: none; text-align: left; padding: 4px var(--sp-2); border-radius: var(--r-sm); cursor: pointer; font-size: var(--fs-xs); color: var(--text-2); }
.strip button:hover { background: var(--surface-2); }
.strip button.cur { background: var(--accent-soft); color: var(--text); }
.sn { width: 28px; color: var(--text-3); }
.moodbar { width: 3px; height: 14px; border-radius: 2px; flex: none; }
.sa { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
</style>
