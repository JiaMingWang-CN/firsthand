<script setup>
import { ref, computed } from 'vue'
import { posts, personas, reads } from '../lib/data.js'
import { P, fmt, browseStart } from '../lib/sim.js'
import { clock, seek, pause } from '../lib/store.js'
import { Lock } from 'lucide-vue-next'
import SimTimeline from '../components/SimTimeline.vue'
import SimTime from '../components/SimTime.vue'
import CommunityPost from '../components/CommunityPost.vue'
import PartTag from '../components/PartTag.vue'
import Avatar from '../components/Avatar.vue'
import PageIntro from '../components/PageIntro.vue'

const t = computed({ get: () => clock.t, set: (v) => seek(v) })
const sort = ref('new')
const permissionsOpen = ref(false)
const visible = computed(() => {
  const list = posts.filter((p) => p.t <= clock.t).map((p) => ({ ...p, comments: p.comments.filter((c) => c.t <= clock.t), seen: readCount(p.id) }))
  return sort.value === 'new' ? list.sort((a, b) => b.t - a.t) : list.sort((a, b) => b.seen - a.seen)
})
function readCount(id) { return reads.filter((r) => r.post === id && r.t <= clock.t).length }
const firstPost = computed(() => [...posts].sort((a, b) => a.t - b.t)[0])
// 体验前的人物只能看帖，不能发言
const canSpeak = (p) => clock.t >= browseStart(p.id) && ['poster', 'commenter'].includes(p.participation)
const permText = (p) => {
  if (clock.t < browseStart(p.id)) return `体验前 · 只能看帖（${fmt(p.slot)} 开始体验）`
  return { poster: '可发帖、评论、点赞', commenter: '可评论、点赞', reactor: '只能点赞', lurker: '只能看帖' }[p.participation]
}
// 权限按当前时刻归类，体验前一律计入只能看帖。
const permissions = computed(() => {
  const counts = { poster: 0, commenter: 0, reactor: 0, lurker: 0 }
  for (const p of personas) counts[clock.t < browseStart(p.id) ? 'lurker' : p.participation]++
  return counts
})
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h1 class="page-title">社区</h1>
        <PageIntro>人物在各自活跃的时段刷社区。这里只显示说出的内容；未说出的与私下问卷只出现在报告和人物档案中。拖动时间轴查看任意时刻的社区。</PageIntro>
      </div>
      <div class="seg" role="group" aria-label="排序">
        <button type="button" :aria-pressed="sort === 'new'" @click="sort = 'new'">最新</button>
        <button type="button" :aria-pressed="sort === 'top'" @click="sort = 'top'">被看最多</button>
      </div>
    </header>

    <SimTimeline v-model="t" @scrub-start="pause" />

    <div class="grid cols">
      <div class="feed">
        <p class="faint small">截至 <SimTime :m="clock.t" />：{{ visible.length }} 条帖子 · {{ visible.reduce((s, p) => s + p.comments.length, 0) }} 条评论</p>
        <TransitionGroup name="rise" tag="div" class="plist">
          <CommunityPost v-for="p in visible" :key="p.id" :post="p" />
        </TransitionGroup>
        <div v-if="!visible.length" class="panel empty">
          <p>到 {{ fmt(clock.t) }} 为止社区里还没有帖子。</p>
          <template v-if="posts.length">
            <p class="faint small">第一条帖子出现在 {{ fmt(firstPost.t) }}，由体验过产品的 {{ P[firstPost.author].realname }} 发出。</p>
            <button class="btn btn-secondary sm" type="button" @click="seek(firstPost.t)">跳到 {{ fmt(firstPost.t) }}</button>
          </template>
          <p v-else class="faint small">这次运行的社区里没有任何公开发言。</p>
        </div>
      </div>

      <aside class="side">
        <section class="panel tight">
          <div class="panel-head"><h3>此刻的发言权限</h3></div>
          <p class="permission-summary">可发帖 {{ permissions.poster }} · 可评论 {{ permissions.commenter }} · 只能点赞 {{ permissions.reactor }} · 只能看帖 {{ permissions.lurker }}</p>
          <button type="button" class="btn btn-ghost sm" :aria-expanded="permissionsOpen" aria-controls="permission-list" @click="permissionsOpen = !permissionsOpen">{{ permissionsOpen ? '收起名单' : '查看名单' }}</button>
          <ul v-if="permissionsOpen" id="permission-list" class="perm">
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
.plist { display: grid; }
h3 { font-size: var(--fs-lg); line-height: 1.5; margin: var(--sp-2) 0 var(--sp-1); }
.permission-summary { margin: 0 0 var(--sp-2); font-size: var(--fs-sm); color: var(--text-2); line-height: 1.7; }
.empty p { margin: 0 0 var(--sp-2); }
.side { display: grid; gap: var(--sp-4); position: sticky; top: 76px; }
.panel-head h3 { font-size: var(--fs-sm); }
.perm { list-style: none; margin: var(--sp-3) 0 0; padding: 0; display: grid; gap: var(--sp-2); }
.perm li { display: flex; align-items: center; gap: var(--sp-2); }
.pn { flex: 1; min-width: 0; display: flex; flex-direction: column; font-size: var(--fs-xs); line-height: 1.4; }
.pn b { font-size: var(--fs-sm); }
.lk { width: 14px; height: 14px; color: var(--text-3); stroke-width: 1.5; }
.pr { gap: var(--sp-3); }
@media (max-width: 1279px) { .cols { grid-template-columns: 1fr; } .side { position: static; } }
</style>
