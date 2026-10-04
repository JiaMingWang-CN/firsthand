<script setup>
import { ref, computed } from 'vue'
import { posts, personas, reads } from '../mock/data.js'
import { P, fmt, votesOf, statusAt, browseStart, label } from '../lib/sim.js'
import { clock, seek, pause, openDrawer } from '../lib/store.js'
import { ThumbsUp, MessageSquare, Eye, Lock } from 'lucide-vue-next'
import SimTimeline from '../components/SimTimeline.vue'
import PersonaChip from '../components/PersonaChip.vue'
import SimTime from '../components/SimTime.vue'
import EvTag from '../components/EvTag.vue'
import PartTag from '../components/PartTag.vue'
import Avatar from '../components/Avatar.vue'

const t = computed({ get: () => clock.t, set: (v) => seek(v) })
const sort = ref('new')
const visible = computed(() => {
  const list = posts.filter((p) => p.t <= clock.t).map((p) => ({ ...p, comments: p.comments.filter((c) => c.t <= clock.t), score: votesOf(p.id, clock.t) }))
  return sort.value === 'new' ? list.sort((a, b) => b.t - a.t) : list.sort((a, b) => b.score - a.score)
})
const readCount = (id) => reads.filter((r) => r.post === id && r.t <= clock.t).length
// 体验前的人物只能看帖，不能发言
const canSpeak = (p) => clock.t >= browseStart(p.id) && ['poster', 'commenter'].includes(p.participation)
const permText = (p) => {
  if (clock.t < browseStart(p.id)) return `体验前 · 只能看帖（${fmt(p.slot)} 开始体验）`
  return { poster: '可发帖、评论、点赞', commenter: '可评论、点赞', reactor: '只能点赞', lurker: '只能看帖' }[p.participation]
}
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <div class="eyebrow">社区 · OASIS Reddit 模式</div>
        <h1 class="page-title">社区</h1>
        <p class="page-sub">人物在各自活跃的时段刷社区。这里只显示说出的内容；未说出的与私下问卷只出现在报告和人物档案中。拖动时间轴查看任意时刻的社区。</p>
      </div>
      <div class="seg" role="group" aria-label="排序">
        <button type="button" :aria-pressed="sort === 'new'" @click="sort = 'new'">最新</button>
        <button type="button" :aria-pressed="sort === 'top'" @click="sort = 'top'">最多赞</button>
      </div>
    </header>

    <SimTimeline v-model="t" @scrub-start="pause" />

    <div class="grid cols">
      <div class="feed">
        <p class="faint small">截至 <SimTime :m="clock.t" />：{{ visible.length }} 条帖子 · {{ visible.reduce((s, p) => s + p.comments.length, 0) }} 条评论</p>
        <TransitionGroup name="rise" tag="div" class="plist">
          <article v-for="p in visible" :key="p.id" class="panel post">
            <div class="vote" :aria-label="`${p.score} 赞`"><ThumbsUp /><b class="num">{{ p.score }}</b></div>
            <div class="pb">
              <div class="row who"><PersonaChip :pid="p.author" /><SimTime :m="p.t" /></div>
              <h3><button type="button" class="pt" @click="openDrawer({ type: 'post', id: p.id })">{{ p.title }}</button></h3>
              <p class="body">{{ p.body }}</p>
              <div class="row meta">
                <span class="mi"><MessageSquare />{{ p.comments.length }}</span>
                <span class="mi"><Eye />被看 {{ readCount(p.id) }} 次</span>
                <span class="sp"></span>
                <EvTag v-for="(ev, i) in p.evidence" :key="i" :ev="ev" />
              </div>
              <div v-if="p.comments.length" class="cmts">
                <div v-for="c in p.comments" :key="c.id" class="cmt">
                  <div class="row who"><PersonaChip :pid="c.author" /><SimTime :m="c.t" /><span class="mi"><ThumbsUp />{{ votesOf(c.id, clock.t) }}</span></div>
                  <p class="cbody">{{ c.body }}</p>
                  <div class="row" v-if="c.evidence.length"><EvTag v-for="(ev, i) in c.evidence" :key="i" :ev="ev" /></div>
                  <div class="row" v-else><span class="tag noev">无证据</span></div>
                </div>
              </div>
            </div>
          </article>
        </TransitionGroup>
        <div v-if="!visible.length" class="panel empty">
          <p>到 {{ fmt(clock.t) }} 为止社区里还没有帖子。</p>
          <p class="faint small">第一条帖子出现在 {{ fmt(posts[0].t) }}，由体验过产品的 {{ P[posts[0].author].realname }} 发出。</p>
          <button class="btn btn-secondary sm" type="button" @click="seek(posts[0].t)">跳到 {{ fmt(posts[0].t) }}</button>
        </div>
      </div>

      <aside class="side">
        <section class="panel tight">
          <div class="panel-head"><h3>此刻的发言权限</h3></div>
          <ul class="perm">
            <li v-for="p in personas" :key="p.id">
              <Avatar :pid="p.id" size="sm" />
              <span class="pn"><b>{{ p.realname }}</b><span class="faint">{{ permText(p) }}</span></span>
              <Lock v-if="!canSpeak(p)" class="lk" aria-label="不能发言" />
            </li>
          </ul>
          <div class="source">没有体验过产品的人物只能看帖，不能发言。看到的帖子会记作体验前的预期。</div>
        </section>
        <section class="panel tight">
          <div class="panel-head"><h3>参与方式</h3></div>
          <div class="row pr"><PartTag kind="poster" /><PartTag kind="commenter" /><PartTag kind="reactor" /><PartTag kind="lurker" /></div>
          <p class="faint small" style="margin-top: var(--sp-2)">不同参与方式对应不同的动作集合；潜水者 {{ personas.filter((p) => p.participation === 'lurker').length }} 人在整个运行中没有任何发言。</p>
        </section>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.cols { grid-template-columns: minmax(0, 1fr) 320px; margin-top: var(--sp-5); align-items: start; }
.small { font-size: var(--fs-xs); margin: 0 0 var(--sp-3); }
.plist { display: grid; gap: var(--sp-3); }
.post { display: grid; grid-template-columns: 40px 1fr; gap: var(--sp-3); }
.vote { display: flex; flex-direction: column; align-items: center; gap: 2px; color: var(--text-2); }
.vote svg { width: 16px; height: 16px; stroke-width: 1.5; }
.pb { min-width: 0; }
.who { gap: var(--sp-2); font-size: var(--fs-xs); }
h3 { font-size: var(--fs-lg); line-height: 1.5; margin: var(--sp-2) 0 var(--sp-1); }
.pt { background: none; border: none; padding: 0; text-align: left; font: inherit; font-weight: 700; color: var(--text); cursor: pointer; }
.pt:hover { text-decoration: underline; text-decoration-color: var(--border-strong); text-underline-offset: 3px; }
.body { margin: 0; font-size: var(--fs-sm); line-height: 1.75; max-width: 720px; }
.meta { margin-top: var(--sp-3); font-size: var(--fs-xs); color: var(--text-3); }
.mi { display: inline-flex; align-items: center; gap: 4px; font-size: var(--fs-xs); color: var(--text-3); }
.mi svg { width: 14px; height: 14px; stroke-width: 1.5; }
.sp { flex: 1; }
.cmts { margin-top: var(--sp-3); display: grid; gap: var(--sp-2); }
.cmt { border-left: 2px solid var(--border); padding: var(--sp-1) var(--sp-3); }
.cbody { margin: 4px 0; font-size: var(--fs-sm); }
.empty p { margin: 0 0 var(--sp-2); }
.side { display: grid; gap: var(--sp-4); position: sticky; top: 76px; }
.panel-head h3 { font-size: var(--fs-sm); }
.perm { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--sp-2); }
.perm li { display: flex; align-items: center; gap: var(--sp-2); }
.pn { flex: 1; min-width: 0; display: flex; flex-direction: column; font-size: var(--fs-xs); line-height: 1.4; }
.pn b { font-size: var(--fs-sm); }
.lk { width: 14px; height: 14px; color: var(--text-3); stroke-width: 1.5; }
.pr { gap: var(--sp-3); }
@media (max-width: 1279px) { .cols { grid-template-columns: 1fr; } .side { position: static; } }
</style>
