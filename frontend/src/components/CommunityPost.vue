<script setup>
import { ref } from 'vue'
import { openDrawer } from '../lib/store.js'
import { useClamp } from '../lib/useClamp.js'
import { MessageSquare, Eye } from 'lucide-vue-next'
import PersonaChip from './PersonaChip.vue'
import SimTime from './SimTime.vue'
import EvidenceGroup from './EvidenceGroup.vue'

const props = defineProps({ post: Object })
const body = ref(null)
const commentsOpen = ref(false)
const { expanded, truncated } = useClamp(() => [body.value], () => props.post.body)
</script>

<template>
  <article class="panel post">
    <div class="pb">
      <div class="row who"><PersonaChip :pid="post.author" /><SimTime :m="post.t" /></div>
      <h3><button type="button" class="pt" @click="openDrawer({ type: 'post', id: post.id })">{{ post.title }}</button></h3>
      <p ref="body" class="body" :class="{ clamped: !expanded }">{{ post.body }}</p>
      <button v-if="truncated" type="button" class="btn btn-ghost sm expand-post" :aria-expanded="expanded" @click="expanded = !expanded">{{ expanded ? '收起' : '展开' }}</button>
      <div class="row meta">
        <button v-if="post.comments.length" type="button" class="mi comments-toggle" :aria-expanded="commentsOpen" :aria-controls="`comments-${post.id}`" @click="commentsOpen = !commentsOpen"><MessageSquare />评论 {{ post.comments.length }}</button>
        <span class="mi"><Eye />被看 {{ post.seen }} 次</span>
        <span class="sp"></span>
        <EvidenceGroup :evidence="post.evidence" />
      </div>
      <div v-if="post.comments.length && commentsOpen" :id="`comments-${post.id}`" class="cmts">
        <div v-for="c in post.comments" :key="c.id" class="cmt">
          <div class="row who"><PersonaChip :pid="c.author" /><SimTime :m="c.t" /></div>
          <p class="cbody">{{ c.body }}</p>
          <EvidenceGroup v-if="c.evidence.length" :evidence="c.evidence" />
          <div class="row" v-else><span class="tag noev">无证据</span></div>
        </div>
      </div>
    </div>
  </article>
</template>

<style scoped>
.post { display: block; padding: var(--sp-4) 0; border-bottom: 1px solid var(--border); }
.pb { min-width: 0; }
.who { gap: var(--sp-2); font-size: var(--fs-xs); }
h3 { font-size: var(--fs-lg); line-height: 1.5; margin: var(--sp-2) 0 var(--sp-1); }
.pt { background: none; border: none; padding: 0; text-align: left; font: inherit; font-weight: 700; color: var(--text); cursor: pointer; }
.pt:hover { text-decoration: underline; text-decoration-color: var(--border-strong); text-underline-offset: 3px; }
.body { margin: 0; font: 15px/1.8 var(--font-serif); max-width: 720px; overflow-wrap: anywhere; }
.clamped { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }
.expand-post { margin-top: var(--sp-1); }
.meta { margin-top: var(--sp-3); font-size: var(--fs-xs); color: var(--text-3); }
.mi { display: inline-flex; align-items: center; gap: 4px; font-size: var(--fs-xs); color: var(--text-3); }
.comments-toggle { border: 0; background: none; padding: 0; cursor: pointer; }
.comments-toggle:hover { color: var(--text); }
.mi svg { width: 14px; height: 14px; stroke-width: 1.5; }
.sp { flex: 1; }
.cmts { margin-top: var(--sp-3); display: grid; gap: var(--sp-2); }
.cmt { border-left: 2px solid var(--border); padding: var(--sp-1) var(--sp-3); }
.cbody { margin: 4px 0; font-size: var(--fs-sm); }
</style>
