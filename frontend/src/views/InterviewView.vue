<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { personas, run } from '../lib/data.js'
import { P } from '../lib/sim.js'
import { openDrawer } from '../lib/store.js'
import { api } from '../api/client.js'
import { Send, Info, BookOpen } from 'lucide-vue-next'
import PersonaCard from '../components/PersonaCard.vue'
import Avatar from '../components/Avatar.vue'
import InterviewEvidence from '../components/InterviewEvidence.vue'
import PageIntro from '../components/PageIntro.vue'

const route = useRoute()
const router = useRouter()
const runId = computed(() => String(route.params.runId))
const pid = computed(() => (P[route.query.pid] ? route.query.pid : personas[0]?.id))
const p = computed(() => P[pid.value])
const threads = ref({})
const draft = ref('')
const busy = ref(false)
const scroller = ref(null)
const msgs = computed(() => threads.value[pid.value] || [])
const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

const STANCE = { declined: '按人设回避', no_experience: '没有亲身体验' }
const defaultQuestions = ['整个体验里你最困惑的是哪一步？为什么？', '有没有什么想说但没在社区里说的？', '你会推荐给别人吗？为什么？', '你是怎么决定结束这次体验的？']

// 服务端不保存会话：把最近几轮已得到回答的问答带上，最多 6 轮
const historyOf = (list) => {
  const turns = []
  for (let i = 0; i + 1 < list.length; i++) if (list[i].role === 'me' && list[i + 1].role === 'them' && list[i + 1].done && !list[i + 1].error) turns.push({ question: list[i].text, answer: list[i + 1].text })
  return turns.slice(-6)
}

async function ask(q) {
  q = (q || draft.value).trim()
  if (!q || busy.value) return
  draft.value = ''
  const who = pid.value
  const list = (threads.value[who] ||= [])
  const history = historyOf(list)
  list.push({ role: 'me', text: q })
  list.push({ role: 'them', text: '', done: false, refs: [], stance: null, error: null })
  const msg = list[list.length - 1]
  busy.value = true
  await scrollDown()
  try {
    const res = await api.interview(runId.value, who, { question: q, history })
    msg.text = res.answer
    msg.refs = res.evidence
    msg.stance = res.stance
  } catch (e) {
    msg.error = failureText(e)
    msg.text = msg.error
  }
  msg.done = true
  busy.value = false
  // 每次采访（含被打回重写的尝试）都记入运行目录之外的采访账本；刷新累计用量
  api.overview(runId.value).then((o) => { run.interviewUsage = o.interview_usage ?? null }).catch(() => {})
  scrollDown()
}
// 只有模型给出了不合格的回答时，换个问法才可能有用；服务出错、超时或配置问题都与问法无关
function failureText(e) {
  if (e.status === 503) return `采访暂不可用：${e.message}`
  if (e.status === 502 && e.reason === 'invalid_answer') return `模型这次没有给出合格的回答，可以换个问法再试。（${e.message}）`
  if (e.status === 502) return `模型服务暂时出错，请稍后再试。（${e.message}）`
  return e.message
}
async function scrollDown() { await nextTick(); scroller.value?.scrollTo({ top: scroller.value.scrollHeight, behavior: reduce ? 'auto' : 'smooth' }) }
const pick = (id) => router.replace({ query: { ...route.query, pid: id } })
const suggestions = computed(() => defaultQuestions.filter((q) => !msgs.value.some((m) => m.text === q)).slice(0, 4))
watch(pid, scrollDown)
</script>

<template>
  <div class="page iv">
    <header class="page-head">
      <div>
        <h1 class="page-title">采访</h1>
        <PageIntro>向任意人物追问。回答基于该人物自己的体验记录和讨论记录，并保持人设语气。报告不依赖采访内容。</PageIntro>
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
          <div class="notice"><Info />模拟人物 · 回答由模型只依据该人物自己的记录生成，不代表真实用户；回答是否被所引记录支持请自行对照</div>
          <div v-if="run.interviewUsage?.total?.requests" class="usage num faint">本次运行的采访累计 {{ run.interviewUsage.total.requests.toLocaleString('zh-CN') }} 次模型请求 · 输入 {{ run.interviewUsage.total.input_tokens.toLocaleString('zh-CN') }}（缓存 {{ run.interviewUsage.total.cached_input_tokens.toLocaleString('zh-CN') }}）· 输出 {{ run.interviewUsage.total.output_tokens.toLocaleString('zh-CN') }} token，不计入运行本身的用量</div>
          <button class="btn btn-secondary sm full" type="button" @click="openDrawer({ type: 'persona', pid, tab: 'record' })"><BookOpen />打开完整体验记录对照</button>
        </div>
        <div class="msgs" ref="scroller" aria-live="polite">
          <p v-if="!msgs.length" class="hint faint">从下面的问题开始，或者输入你自己的问题。</p>
          <div v-for="(m, i) in msgs" :key="i" class="msg" :class="m.role">
            <Avatar v-if="m.role === 'them'" :pid="pid" size="sm" />
            <div class="bubble">
              <span v-if="m.role === 'them' && !m.text" class="typing"><i></i><i></i><i></i></span>
              {{ m.text }}
              <div v-if="m.role === 'them' && m.stance && STANCE[m.stance]" class="row evs"><span class="tag">{{ STANCE[m.stance] }}</span></div>
              <InterviewEvidence v-if="m.role === 'them' && m.done && m.refs.length" :run-id="runId" :refs="m.refs" />
              <p v-if="m.role === 'them' && m.done && !m.error && !m.refs.length && m.stance === 'answered'" class="faint noev">这条回答没有引用证据。</p>
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
.pi.on { background: var(--surface-2); box-shadow: inset 2px 0 0 var(--signal); color: var(--text); font-weight: 600; }
.pn { flex: 1; }
.cnt { font-size: var(--fs-xs); color: var(--text-3); }
.chat { display: flex; flex-direction: column; height: calc(100vh - 210px); min-height: 520px; }
.ch { padding: var(--sp-4) var(--sp-5); border-bottom: 1px solid var(--border); display: grid; grid-template-columns: 1fr auto; gap: var(--sp-3); align-items: start; }
.notice { grid-column: 1; display: flex; align-items: center; gap: 6px; font-size: var(--fs-xs); color: var(--sim); }
.notice svg { width: 14px; height: 14px; stroke-width: 1.5; }
.usage { grid-column: 1; font-size: var(--fs-xs); }
.ch .full { grid-column: 2; grid-row: 1; }
.msgs { flex: 1; overflow-y: auto; padding: var(--sp-5); display: flex; flex-direction: column; gap: var(--sp-4); }
.hint { text-align: center; margin: auto; font-size: var(--fs-sm); }
.msg { display: flex; gap: var(--sp-2); align-items: flex-end; max-width: 78%; }
.msg.me { align-self: flex-end; }
.bubble { padding: var(--sp-2) var(--sp-4); font-size: var(--fs-md); line-height: 1.8; }
.them .bubble { padding: 2px 0 2px 14px; border-left: 2px solid var(--border-strong); font-family: var(--font-serif); color: var(--text); }
.me .bubble { background: var(--surface-2); color: var(--text); font-weight: 600; }
.evs { margin-top: var(--sp-2); font-size: var(--fs-xs); }
.typing { display: inline-flex; gap: 4px; padding: 4px 0; }
.typing i { width: 6px; height: 6px; border-radius: 50%; background: var(--text-3); animation: pulse 1s var(--ease) infinite; display: block; }
.typing i:nth-child(2) { animation-delay: .15s; } .typing i:nth-child(3) { animation-delay: .3s; }
.composer { border-top: 1px solid var(--border); padding: var(--sp-3) var(--sp-5) var(--sp-4); }
.sugg { margin-bottom: var(--sp-3); gap: var(--sp-2); }
.sq { border: 1px solid var(--border-strong); background: var(--surface); border-radius: 0; padding: 3px 12px; font-size: var(--fs-xs); cursor: pointer; color: var(--text-2); }
.sq:hover:not(:disabled) { border-color: var(--ink); color: var(--text); background: var(--surface-2); }
.inputrow { flex-wrap: nowrap; }
@media (max-width: 959px) {
  .wrap { grid-template-columns: 1fr; }
  .plist { position: static; flex-direction: row; overflow-x: auto; }
  .ch { grid-template-columns: 1fr; } .ch .full { grid-column: 1; grid-row: auto; }
  .msg { max-width: 92%; }
}
</style>
