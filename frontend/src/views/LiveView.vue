<script setup>
import { ref, computed, watch } from 'vue'
import { personas, steps, posts } from '../lib/data.js'
import { P, fmt, statusAt, stepIndexAt, browseStart, feedUntil, postById, label, assignmentLabel } from '../lib/sim.js'
import { clock, seek, pause, play, openDrawer } from '../lib/store.js'
import { Play, SkipForward, Eye, ThumbsUp, MessageSquare, FileText } from 'lucide-vue-next'
import SimTimeline from '../components/SimTimeline.vue'
import Shot from '../components/Shot.vue'
import PersonaChip from '../components/PersonaChip.vue'
import Avatar from '../components/Avatar.vue'
import StatusDot from '../components/StatusDot.vue'
import SimTime from '../components/SimTime.vue'
import EmotionCurve from '../components/EmotionCurve.vue'
import PageIntro from '../components/PageIntro.vue'

const t = computed({ get: () => clock.t, set: (v) => seek(v) })
const browsing = computed(() => personas.filter((p) => statusAt(p.id, clock.t) === 'browse'))
const pinned = ref(null)
const focusId = computed(() => {
  if (pinned.value) return pinned.value
  if (browsing.value.length) return browsing.value[0].id
  const started = personas.filter((p) => browseStart(p.id) <= clock.t).sort((a, b) => browseStart(b.id) - browseStart(a.id))
  return started[0]?.id || personas[0]?.id
})
const fp = computed(() => P[focusId.value])
const idx = computed(() => stepIndexAt(focusId.value, clock.t))
const cur = computed(() => (idx.value >= 0 ? steps[focusId.value][idx.value] : null))
const focusStatus = computed(() => statusAt(focusId.value, clock.t))
const next = computed(() => personas.filter((p) => browseStart(p.id) > clock.t).sort((a, b) => a.slot - b.slot)[0])
const historyOpen = ref(false)
const feedOpen = ref(false)
const peopleOpen = ref(false)
// 优先列出最近开始体验的人物，尚未开始的人物按体验时间补足。
const recentPeople = computed(() => [
  ...personas.filter((p) => p.slot <= clock.t).sort((a, b) => b.slot - a.slot),
  ...personas.filter((p) => p.slot > clock.t).sort((a, b) => a.slot - b.slot),
].slice(0, 5))
watch(focusId, () => { historyOpen.value = false })
const history = computed(() => (idx.value >= 0 ? steps[focusId.value].slice(0, idx.value + 1).map((s, i) => ({ ...s, i })).reverse() : []))

// 社区动态：新内容出现时不自动插入，只提示“有 n 条新动态”
const shownKeys = ref(new Set(feedUntil(clock.t).map((e) => e.ref + e.t)))
const full = computed(() => feedUntil(clock.t))
const pending = computed(() => full.value.filter((e) => !shownKeys.value.has(e.ref + e.t)))
const feed = computed(() => full.value.filter((e) => shownKeys.value.has(e.ref + e.t)))
watch(() => clock.t, (nt, ot) => { if (nt < ot - 1) shownKeys.value = new Set(feedUntil(nt).map((e) => e.ref + e.t)) })
function reveal() { shownKeys.value = new Set(full.value.map((e) => e.ref + e.t)) }

const textOf = (e) => {
  if (e.kind === 'post') return postById[e.ref].title
  const c = posts.flatMap((p) => p.comments).find((x) => x.id === e.ref)
  if (e.kind === 'comment') return c.body
  return postById[e.ref]?.title || c?.body
}
const kindIcon = { post: FileText, comment: MessageSquare, react: ThumbsUp }
const kindName = { post: '发帖', comment: '评论', react: '点赞' }
function openFeed(e) {
  const postId = e.kind === 'post' ? e.ref : e.kind === 'comment' ? e.post : postById[e.ref] ? e.ref : posts.find((p) => p.comments.some((c) => c.id === e.ref)).id
  openDrawer({ type: 'post', id: postId, focus: e.ref })
}
function jumpNext() { if (next.value) { seek(next.value.slot); pinned.value = null } }
function progressOf(pid) {
  const i = stepIndexAt(pid, clock.t)
  return { n: i + 1, max: P[pid].maxSteps }
}
function activityOf(pid) {
  const st = statusAt(pid, clock.t)
  if (st === 'browse') return steps[pid][stepIndexAt(pid, clock.t)].act
  if (st === 'wait') return `${fmt(P[pid].slot)} 开始体验`
  if (st === 'social') return '在社区看帖或发言'
  return P[pid].outcomeReason
}
</script>

<template>
  <div class="page live">
    <header class="page-head">
      <div>
        <h1 class="page-title">运行现场</h1>
        <PageIntro>拖动播放头回到任意模拟时刻：人物状态、实时画面和社区动态会同步到该时刻。当前选中的时刻已同步到链接中，可直接分享。</PageIntro>
      </div>
    </header>

    <SimTimeline v-model="t" rows show-activity @scrub-start="pause" />

    <div class="grid stage">
      <!-- 实时画面 -->
      <section class="panel screen-panel">
        <div class="panel-head">
          <PersonaChip :pid="focusId" />
          <StatusDot :status="focusStatus" />
          <span class="tag"><Eye />围观 · 只读</span>
          <span class="aside row">
            <span class="faint num" v-if="cur">步骤 #{{ idx + 1 }} / 上限 {{ fp.maxSteps }}</span>
            <button v-if="pinned" class="btn btn-ghost sm" type="button" @click="pinned = null">自动跟随</button>
          </span>
        </div>
        <div class="screenwrap" :class="fp.device">
          <Shot v-if="cur" :step="cur" :device="fp.device" :time="fmt(cur.t).slice(3)" :live="focusStatus === 'browse'" />
          <div v-else class="empty-screen">
            <p>{{ fp.realname }} 还没有开始体验</p>
            <SimTime :m="fp.slot" prefix="开始于" />
          </div>
          <div v-if="!browsing.length && next" class="idle">
            <span>当前没有人物在体验。下一位：</span>
            <PersonaChip :pid="next.id" /><SimTime :m="next.slot" />
            <button class="btn btn-secondary sm" type="button" @click="jumpNext"><SkipForward />跳到该时刻</button>
          </div>
        </div>
        <div v-if="cur" class="now">
          <div class="nowact">{{ cur.act }}</div>
          <div class="nowthink" v-if="cur.think">“{{ cur.think }}”<span class="faint"> · 体验记录中的想法</span></div>
          <div class="row ctx">
            <span class="tag">{{ assignmentLabel(fp) }}</span>
            <span class="tag">{{ label.device[fp.device] }}</span>
            <span class="tag">{{ label.patience[fp.patience] }}</span>
            <span class="faint state">体验时状态：{{ fp.state }}</span>
          </div>
        </div>
      </section>

      <!-- 人物状态 -->
      <section class="panel flush people">
        <div class="ph"><h3>人物</h3><span class="faint num">{{ browsing.length }} 人体验中</span></div>
        <ul>
          <li v-for="p in (peopleOpen ? personas : recentPeople)" :key="p.id" :class="{ sel: focusId === p.id }">
            <button type="button" @click="pinned = p.id" :aria-label="`查看 ${p.realname} 的实时画面`">
              <Avatar :pid="p.id" size="sm" />
              <span class="pn">
                <span class="row nm"><b>{{ p.realname }}</b><StatusDot :status="statusAt(p.id, clock.t)" /></span>
                <span class="pa">{{ activityOf(p.id) }}</span>
              </span>
              <span class="pg num" v-if="statusAt(p.id, clock.t) !== 'wait'">
                <span class="pbar"><i :style="{ width: Math.min(100, (progressOf(p.id).n / progressOf(p.id).max) * 100) + '%', background: p.color }"></i></span>
                {{ progressOf(p.id).n }}/{{ progressOf(p.id).max }}
              </span>
            </button>
          </li>
        </ul>
        <button v-if="personas.length > 5" class="btn btn-ghost sm" type="button" :aria-expanded="peopleOpen" @click="peopleOpen = !peopleOpen">{{ peopleOpen ? '收起' : `显示全部 ${personas.length} 人` }}</button>
      </section>
    </div>

    <div class="grid g2 lower">
      <section class="panel">
        <div class="panel-head"><h3>步骤日志 · {{ fp.realname }}</h3><span class="aside faint num">{{ history.length }} 步</span></div>
        <ol v-if="history.length" class="log">
          <TransitionGroup name="rise">
            <li v-for="s in (historyOpen ? history : history.slice(0, 5))" :key="s.i">
              <button type="button" @click="openDrawer({ type: 'evidence', ev: { pid: focusId, step: s.i + 1, kind: 'step' } })">
                <span class="num sn">#{{ s.i + 1 }}</span><span class="num st">{{ fmt(s.t).slice(3) }}</span>
                <span class="mb" :style="{ background: s.sat >= .3 ? 'var(--pos)' : s.sat <= -.3 ? 'var(--neg)' : 'var(--border-strong)' }"></span>
                <span class="sa">{{ s.act }}</span>
              </button>
            </li>
          </TransitionGroup>
        </ol>
        <p v-else class="faint small">到达体验时刻后，这里会逐条出现步骤。</p>
        <button v-if="history.length > 5" class="btn btn-ghost sm" type="button" :aria-expanded="historyOpen" @click="historyOpen = !historyOpen">{{ historyOpen ? '收起' : `显示全部 ${history.length} 步` }}</button>
        <EmotionCurve v-if="history.length" :pids="[focusId]" :up-to="clock.t" :active-step="idx + 1" :height="110" title="情绪曲线（截至当前时刻）" />
      </section>

      <section class="panel">
        <div class="panel-head"><h3>社区动态</h3><span class="aside faint">只显示说出的内容</span></div>
        <button v-if="pending.length" class="newpill" type="button" @click="reveal">有 {{ pending.length }} 条新动态</button>
        <ul v-if="feed.length" class="feed">
          <li v-for="e in (feedOpen ? feed : feed.slice(0, 5))" :key="e.ref + e.t" :class="e.kind">
            <button type="button" @click="openFeed(e)">
              <component :is="kindIcon[e.kind]" class="fi" />
              <span class="fb">
                <span class="row fm"><PersonaChip :pid="e.pid" no-hover /><span class="faint">{{ kindName[e.kind] }}</span><SimTime :m="e.t" /></span>
                <span class="ft" :class="{ dim: e.kind === 'react' }">{{ textOf(e) }}</span>
              </span>
            </button>
          </li>
        </ul>
        <div v-else class="empty-feed">
          <p class="faint small">到 {{ fmt(clock.t) }} 为止还没有人发言。</p>
          <button v-if="!clock.playing" class="btn btn-secondary sm" type="button" @click="play"><Play />播放回放</button>
        </div>
        <button v-if="feed.length > 5" class="btn btn-ghost sm" type="button" :aria-expanded="feedOpen" @click="feedOpen = !feedOpen">{{ feedOpen ? '收起' : `显示全部 ${feed.length} 条` }}</button>
      </section>
    </div>
  </div>
</template>

<style scoped>
.stage { grid-template-columns: minmax(0, 1fr) 360px; margin-top: var(--sp-4); align-items: start; }
.screen-panel .panel-head .tag svg { width: 12px; height: 12px; }
.screenwrap { position: relative; background: var(--surface-2); border-radius: var(--r-md); padding: var(--sp-4); display: flex; justify-content: center; }
.screenwrap > :deep(.shot) { width: 100%; }
.screenwrap.mobile > :deep(.shot) { width: 300px; }
.empty-screen { aspect-ratio: 16 / 10; width: 100%; display: grid; place-content: center; justify-items: center; gap: var(--sp-2); color: var(--text-2); }
.idle { position: absolute; left: 50%; bottom: var(--sp-5); transform: translateX(-50%); background: var(--surface); border: 1px solid var(--border); box-shadow: var(--shadow-2); border-radius: var(--r-lg); padding: var(--sp-2) var(--sp-3); display: flex; align-items: center; gap: var(--sp-2); font-size: var(--fs-sm); white-space: nowrap; z-index: 3; }
.now { margin-top: var(--sp-4); }
.nowact { font-size: var(--fs-lg); font-weight: 600; }
.nowthink { color: var(--text); font-size: var(--fs-sm); margin-top: 4px; }
.ctx { margin-top: var(--sp-3); gap: 6px; }
.state { font-size: var(--fs-xs); }
.people .ph { display: flex; align-items: center; justify-content: space-between; padding: var(--sp-4) var(--sp-4) var(--sp-2); }
.people h3 { font-size: var(--fs-lg); }
.people ul { list-style: none; margin: 0; padding: 0 var(--sp-2) var(--sp-2); }
.people li button { width: 100%; display: flex; align-items: center; gap: var(--sp-3); padding: var(--sp-2); border: none; background: none; border-radius: var(--r-md); cursor: pointer; text-align: left; }
.people li button:hover { background: var(--surface-2); }
.people li.sel button { background: var(--accent-soft); }
.pn { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.nm { gap: var(--sp-2); flex-wrap: nowrap; font-size: var(--fs-sm); }
.pa { font-size: var(--fs-xs); color: var(--text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pg { display: flex; flex-direction: column; align-items: flex-end; gap: 3px; font-size: var(--fs-xs); color: var(--text-3); width: 48px; flex: none; }
.pbar { width: 48px; height: 3px; border-radius: 0; background: var(--surface-2); overflow: hidden; display: block; }
.pbar i { display: block; height: 100%; transition: width var(--dur) linear; }
.lower { margin-top: var(--sp-4); align-items: start; }
.log { list-style: none; padding: 0; margin: 0 0 var(--sp-3); max-height: 260px; overflow-y: auto; }
.log button { width: 100%; display: flex; align-items: center; gap: var(--sp-2); border: none; background: none; text-align: left; padding: 5px var(--sp-2); border-radius: var(--r-sm); cursor: pointer; font-size: var(--fs-sm); }
.log button:hover { background: var(--surface-2); }
.sn { width: 28px; color: var(--text-3); font-size: var(--fs-xs); }
.st { width: 40px; color: var(--sim); font-size: var(--fs-xs); }
.mb { width: 3px; height: 16px; border-radius: 0; flex: none; }
.sa { flex: 1; min-width: 0; }
.small { font-size: var(--fs-xs); }
.newpill { display: block; margin: 0 auto var(--sp-3); border: 1px solid var(--accent); color: var(--accent); background: var(--accent-soft); border-radius: 0; padding: 2px 14px; font-size: var(--fs-xs); font-weight: 600; cursor: pointer; }
.feed { list-style: none; padding: 0; margin: 0; max-height: 420px; overflow-y: auto; }
.feed li button { width: 100%; display: flex; gap: var(--sp-3); border: none; background: none; text-align: left; padding: var(--sp-2); border-radius: var(--r-md); cursor: pointer; }
.feed li button:hover { background: var(--surface-2); }
.fi { width: 16px; height: 16px; stroke-width: 1.5; color: var(--text-3); flex: none; margin-top: 3px; }
.fb { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.fm { gap: var(--sp-2); font-size: var(--fs-xs); }
.ft { font-size: var(--fs-sm); color: var(--text); }
.ft.dim { color: var(--text-2); font-size: var(--fs-xs); }
.empty-feed { display: grid; justify-items: start; gap: var(--sp-2); }
@media (max-width: 1100px) { .lower { grid-template-columns: 1fr; } .idle { max-width: 100%; flex-wrap: wrap; white-space: normal; width: max-content; } }
@media (max-width: 1279px) { .stage { grid-template-columns: 1fr; } }
</style>
