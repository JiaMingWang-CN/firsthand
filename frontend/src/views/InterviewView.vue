<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { personas, steps, surveys, interviewScripts, defaultQuestions } from '../mock/data.js'
import { P, assignmentLabel, withheldFor } from '../lib/sim.js'
import { openDrawer } from '../lib/store.js'
import { Send, Info, BookOpen } from 'lucide-vue-next'
import PersonaCard from '../components/PersonaCard.vue'
import Avatar from '../components/Avatar.vue'
import EvTag from '../components/EvTag.vue'

const route = useRoute()
const router = useRouter()
const pid = computed(() => (P[route.query.pid] ? route.query.pid : 'p1'))
const p = computed(() => P[pid.value])
const threads = ref({})
const draft = ref('')
const busy = ref(false)
const scroller = ref(null)
const msgs = computed(() => threads.value[pid.value] || [])
const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

function answerFor(q) {
  const script = interviewScripts[pid.value]?.find((x) => x.q === q)
  if (script) return { text: script.a, ev: script.ev }
  const s = steps[pid.value], sv = surveys[pid.value], me = p.value
  if (/放弃/.test(q)) {
    if (me.outcome !== 'quit') return { text: `我没放弃啊。${me.outcomeReason}`, ev: [{ pid: pid.value, step: s.length, kind: 'step' }] }
    return { text: me.outcomeReason, ev: [{ pid: pid.value, step: s.length, kind: 'step' }] }
  }
  if (/困惑|卡|难/.test(q)) {
    const i = s.reduce((bi, x, k) => (x.conf > s[bi].conf ? k : bi), 0)
    return { text: `第 ${i + 1} 步吧，${s[i].act}。${s[i].think ? '当时就觉得：' + s[i].think : ''}`, ev: [{ pid: pid.value, step: i + 1, kind: 'step' }] }
  }
  if (/没说|没在社区/.test(q)) {
    const w = withheldFor(pid.value)
    if (!w.length) return { text: '没有，想说的都说了。', ev: [] }
    if (me.withhold === '高') return { text: '也没什么特别的吧……就是整体用下来还行。', ev: [] }
    return { text: `有一点。${w[0].item}当时没好意思说。`, ev: w[0].evidence }
  }
  if (/推荐/.test(q)) {
    return { text: sv.nps >= 9 ? `会，${sv.best}确实好用。` : sv.nps >= 7 ? `可能会，不过${sv.worst}得先改改。` : `暂时不会。主要是${sv.worst}。`, ev: [] }
  }
  return { text: `这个我没太留意。我这次主要是在「${assignmentLabel(me)}」，印象最深的是${sv.worst}。`, ev: [] }
}

async function ask(q) {
  q = (q || draft.value).trim()
  if (!q || busy.value) return
  draft.value = ''
  const list = (threads.value[pid.value] ||= [])
  list.push({ role: 'me', text: q })
  const ans = answerFor(q)
  const msg = { role: 'them', text: '', full: ans.text, ev: ans.ev, done: false }
  list.push(msg)
  busy.value = true
  await scrollDown()
  const m = list[list.length - 1]
  if (reduce) { m.text = m.full } else {
    await new Promise((r) => setTimeout(r, 450))
    for (let i = 1; i <= m.full.length; i += 2) { m.text = m.full.slice(0, i); await new Promise((r) => setTimeout(r, 18)) }
    m.text = m.full
  }
  m.done = true
  busy.value = false
  scrollDown()
}
async function scrollDown() { await nextTick(); scroller.value?.scrollTo({ top: scroller.value.scrollHeight, behavior: reduce ? 'auto' : 'smooth' }) }
const pick = (id) => router.replace({ query: { ...route.query, pid: id } })
const suggestions = computed(() => {
  const own = (interviewScripts[pid.value] || []).map((x) => x.q)
  return [...new Set([...own, ...defaultQuestions])].filter((q) => !msgs.value.some((m) => m.text === q)).slice(0, 4)
})
watch(pid, scrollDown)
</script>

<template>
  <div class="page iv">
    <header class="page-head">
      <div>
        <div class="eyebrow">采访</div>
        <h1 class="page-title">采访</h1>
        <p class="page-sub">向任意人物追问。回答基于该人物自己的体验记录和讨论记录，并保持人设语气。报告不依赖采访内容。</p>
      </div>
    </header>

    <div class="wrap">
      <aside class="plist" aria-label="选择人物">
        <button v-for="x in personas" :key="x.id" type="button" class="pi" :class="{ on: x.id === pid }" @click="pick(x.id)">
          <Avatar :pid="x.id" size="sm" /><span class="pn">{{ x.realname }}</span>
          <span v-if="threads[x.id]?.length" class="cnt num">{{ threads[x.id].length / 2 }}</span>
        </button>
      </aside>

      <section class="panel flush chat">
        <div class="ch">
          <PersonaCard :pid="pid" compact />
          <div class="notice"><Info />模拟人物 · 回答由模型基于体验记录生成，不代表真实用户</div>
          <button class="btn btn-secondary sm full" type="button" @click="openDrawer({ type: 'persona', pid, tab: 'record' })"><BookOpen />打开完整体验记录对照</button>
        </div>
        <div class="msgs" ref="scroller" aria-live="polite">
          <p v-if="!msgs.length" class="hint faint">从下面的问题开始，或者输入你自己的问题。</p>
          <div v-for="(m, i) in msgs" :key="i" class="msg" :class="m.role">
            <Avatar v-if="m.role === 'them'" :pid="pid" size="sm" />
            <div class="bubble">
              <span v-if="m.role === 'them' && !m.text" class="typing"><i></i><i></i><i></i></span>
              {{ m.text }}
              <div v-if="m.role === 'them' && m.done && m.ev.length" class="row evs"><span class="faint">引用的体验</span><EvTag v-for="(e, k) in m.ev" :key="k" :ev="e" /></div>
            </div>
          </div>
        </div>
        <div class="composer">
          <div class="row sugg">
            <button v-for="q in suggestions" :key="q" type="button" class="sq" :disabled="busy" @click="ask(q)">{{ q }}</button>
          </div>
          <form class="row inputrow" @submit.prevent="ask()">
            <input v-model="draft" class="input grow" data-search :placeholder="`问 ${p.realname} 一个问题…`" aria-label="输入问题" />
            <button class="btn btn-primary" type="submit" :disabled="busy || !draft.trim()"><Send />发送问题</button>
          </form>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.wrap { display: grid; grid-template-columns: 180px minmax(0, 1fr); gap: var(--sp-4); align-items: start; }
.plist { display: flex; flex-direction: column; gap: 2px; position: sticky; top: var(--sp-5); }
.pi { display: flex; align-items: center; gap: var(--sp-2); border: none; background: none; padding: 6px var(--sp-2); border-radius: var(--r-md); cursor: pointer; text-align: left; font-size: var(--fs-sm); color: var(--text-2); }
.pi:hover { background: var(--surface-2); color: var(--text); }
.pi.on { background: var(--surface); box-shadow: inset 0 0 0 1px var(--border); color: var(--text); font-weight: 600; }
.pn { flex: 1; }
.cnt { font-size: var(--fs-xs); color: var(--text-3); }
.chat { display: flex; flex-direction: column; height: calc(100vh - 210px); min-height: 520px; }
.ch { padding: var(--sp-4) var(--sp-5); border-bottom: 1px solid var(--border); display: grid; grid-template-columns: 1fr auto; gap: var(--sp-3); align-items: start; }
.notice { grid-column: 1; display: flex; align-items: center; gap: 6px; font-size: var(--fs-xs); color: var(--sim); }
.notice svg { width: 14px; height: 14px; stroke-width: 1.5; }
.ch .full { grid-column: 2; grid-row: 1; }
.msgs { flex: 1; overflow-y: auto; padding: var(--sp-5); display: flex; flex-direction: column; gap: var(--sp-4); }
.hint { text-align: center; margin: auto; font-size: var(--fs-sm); }
.msg { display: flex; gap: var(--sp-2); align-items: flex-end; max-width: 78%; }
.msg.me { align-self: flex-end; }
.bubble { padding: var(--sp-3) var(--sp-4); border-radius: var(--r-lg); font-size: var(--fs-md); line-height: 1.7; }
.them .bubble { background: var(--surface-2); color: var(--text); border-bottom-left-radius: var(--r-sm); }
.me .bubble { background: var(--accent-soft); color: var(--text); border-bottom-right-radius: var(--r-sm); }
.evs { margin-top: var(--sp-2); font-size: var(--fs-xs); }
.typing { display: inline-flex; gap: 4px; padding: 4px 0; }
.typing i { width: 6px; height: 6px; border-radius: 50%; background: var(--text-3); animation: pulse 1s var(--ease) infinite; display: block; }
.typing i:nth-child(2) { animation-delay: .15s; } .typing i:nth-child(3) { animation-delay: .3s; }
.composer { border-top: 1px solid var(--border); padding: var(--sp-3) var(--sp-5) var(--sp-4); }
.sugg { margin-bottom: var(--sp-3); gap: var(--sp-2); }
.sq { border: 1px solid var(--border-strong); background: var(--surface); border-radius: var(--r-full); padding: 3px 12px; font-size: var(--fs-xs); cursor: pointer; color: var(--text-2); }
.sq:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.inputrow { flex-wrap: nowrap; }
@media (max-width: 959px) {
  .wrap { grid-template-columns: 1fr; }
  .plist { position: static; flex-direction: row; overflow-x: auto; }
  .ch { grid-template-columns: 1fr; } .ch .full { grid-column: 1; grid-row: auto; }
  .msg { max-width: 92%; }
}
</style>
