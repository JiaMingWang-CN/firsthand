<script setup>
import { computed } from 'vue'
import { reads } from '../lib/data.js'
import { postById } from '../lib/sim.js'
import { Eye } from 'lucide-vue-next'
import PersonaChip from './PersonaChip.vue'
import SimTime from './SimTime.vue'
import EvTag from './EvTag.vue'

const props = defineProps({ id: String, focus: String })
const post = computed(() => postById[props.id])
const readers = computed(() => reads.filter((r) => r.post === props.id).sort((a, b) => a.t - b.t))
</script>

<template>
  <div>
    <div class="note small">社区视图只显示人物说出的内容。未说出的与私下问卷只在报告和人物档案中出现。</div>
    <article class="post" :class="{ focus: focus === post.id }">
      <div class="row who"><PersonaChip :pid="post.author" /><SimTime :m="post.t" /><span class="faint">发帖</span></div>
      <h2 class="t">{{ post.title }}</h2>
      <p class="body">{{ post.body }}</p>
      <div class="row foot">
        <span class="votes"><Eye />被看 {{ readers.length }} 次</span>
        <span class="sp"></span>
        <EvTag v-for="(ev, i) in post.evidence" :key="i" :ev="ev" />
      </div>
    </article>

    <div class="label sec">评论 {{ post.comments.length }}</div>
    <div class="comments">
      <div v-for="c in post.comments" :key="c.id" class="cmt" :class="{ focus: focus === c.id }">
        <div class="row who"><PersonaChip :pid="c.author" /><SimTime :m="c.t" /></div>
        <p class="body">{{ c.body }}</p>
        <div class="row" v-if="c.evidence.length"><span class="faint ev-k">依据的体验</span><EvTag v-for="(ev, i) in c.evidence" :key="i" :ev="ev" /></div>
        <div class="row" v-else><span class="tag noev">无证据</span><span class="faint ev-k">这条评论没有对应的体验步骤</span></div>
      </div>
    </div>

    <div class="label sec">看过这条帖子的人物 {{ readers.length }}</div>
    <div class="readers">
      <div v-for="r in readers" :key="r.pid + r.t" class="rd">
        <PersonaChip :pid="r.pid" /><SimTime :m="r.t" />
        <span class="faint">{{ r.before ? '体验前看到' : '体验后看到' }}</span>
        <p v-if="r.expectation" class="exp">形成预期：{{ r.expectation }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.small { font-size: var(--fs-xs); margin-bottom: var(--sp-4); }
.post { border: 1px solid var(--border); border-radius: var(--r-lg); padding: var(--sp-4); }
.focus { box-shadow: 0 0 0 2px var(--accent); }
.who { gap: var(--sp-2); font-size: var(--fs-xs); }
.t { font-size: var(--fs-lg); line-height: 1.5; margin: var(--sp-2) 0; }
.body { margin: var(--sp-2) 0; font-size: var(--fs-sm); line-height: 1.75; }
.foot { margin-top: var(--sp-3); font-size: var(--fs-xs); }
.votes { display: inline-flex; align-items: center; gap: 4px; font-size: var(--fs-xs); color: var(--text-2); }
.votes svg { width: 14px; height: 14px; stroke-width: 1.5; }
.sp { flex: 1; }
.sec { margin: var(--sp-5) 0 var(--sp-2); }
.comments { display: grid; gap: var(--sp-2); }
.cmt { border-left: 2px solid var(--border); padding: var(--sp-2) var(--sp-3); border-radius: 0 var(--r-md) var(--r-md) 0; }
.ev-k { font-size: var(--fs-xs); }
.readers { display: grid; gap: var(--sp-2); }
.rd { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-2); font-size: var(--fs-xs); }
.exp { width: 100%; margin: 0 0 var(--sp-2); background: var(--sim-soft); padding: var(--sp-2) var(--sp-3); border-radius: var(--r-md); font-size: var(--fs-xs); color: var(--text); }
</style>
