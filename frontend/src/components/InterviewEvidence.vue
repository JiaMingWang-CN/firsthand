<script setup>
// 采访回答所引证据的原文展开。回答是否被这些记录支持，由读者对照判断，系统不自评。
import { ref, watch } from 'vue'
import { api } from '../api/client.js'
import { openDrawer } from '../lib/store.js'

const props = defineProps({ runId: { type: String, required: true }, refs: { type: Array, required: true } })
const items = ref([])
const loading = ref(true)

const SURVEY = { nps: '推荐意愿', continue_using: '继续使用', would_pay: '付费意愿', biggest_issue: '最大的问题', favorite: '最喜欢', unsaid: '没说出口的', opinion_changed: '观点是否被改变', influencing_post_ids: '影响观点的帖子', explanation: '问卷说明' }

function describe(ref_, rec) {
  const d = rec.data
  if (rec.category === 'experience') {
    const step = /:step:(\d+)$/.exec(ref_)
    if (step) return { kind: `步骤 #${step[1]}`, text: d.agent_observation, step: Number(step[1]) }
    if (ref_.endsWith(':outcome')) return { kind: '任务结果', text: d.reason }
    return { kind: d.kind === 'pain' ? '痛点' : '亮点', text: d.title, detail: d.description, quote: d.observed_quote, step: rec.steps?.[0] }
  }
  if (rec.category === 'reads') return { kind: d.before_experience ? '体验前读到的帖子' : '读过的帖子', text: d.post?.content }
  if (rec.category === 'discussion') return { kind: '本人在社区的发言', text: d.content }
  if (rec.category === 'withheld') {
    const reasons = d.withheld.map((w) => w.reason).filter(Boolean)
    return { kind: '表达过滤决定', text: `公开 ${d.shared.length} 条，保留 ${d.withheld.length} 条${reasons.length ? `：${reasons.join('；')}` : ''}`, detail: d.public_body }
  }
  if (rec.category === 'surveys') {
    const [field, value] = Object.entries(d)[0] ?? []
    return { kind: '私下问卷', text: `${SURVEY[field] ?? field}：${typeof value === 'object' ? JSON.stringify(value) : value}` }
  }
  return { kind: rec.category, text: '' }
}

async function load() {
  loading.value = true
  items.value = await Promise.all(props.refs.map(async (r) => {
    try {
      const rec = await api.evidence(props.runId, r)
      return { ref: r, pid: rec.persona_id, files: rec.files ?? [], ...describe(r, rec) }
    } catch (e) {
      return { ref: r, error: e.message }
    }
  }))
  loading.value = false
}
watch(() => [props.runId, props.refs], load, { immediate: true })
</script>

<template>
  <details class="iev" open>
    <summary>所引证据 · {{ refs.length }} 条（请对照原文判断回答是否站得住）</summary>
    <p v-if="loading" class="faint small">正在读取证据原文…</p>
    <ul v-else>
      <li v-for="it in items" :key="it.ref">
        <div class="row head">
          <span class="tag">{{ it.kind ?? '证据' }}</span>
          <span class="num faint ref">{{ it.ref }}</span>
          <button v-if="it.step" class="btn btn-ghost sm" type="button" @click="openDrawer({ type: 'evidence', ev: { pid: it.pid, step: it.step, kind: 'step' } })">查看对应步骤</button>
        </div>
        <p v-if="it.error" class="err">无法读取：{{ it.error }}</p>
        <template v-else>
          <p class="txt">{{ it.text }}</p>
          <p v-if="it.quote" class="quote"><span class="faint">页面原文：</span>“{{ it.quote }}”</p>
          <p v-if="it.detail" class="detail faint">{{ it.detail }}</p>
          <div v-if="it.files.length" class="shots">
            <a v-for="f in it.files.slice(0, 2)" :key="f" :href="f" target="_blank" rel="noopener" aria-label="在新标签打开截图"><img :src="f" alt="证据截图" loading="lazy" /></a>
          </div>
        </template>
      </li>
    </ul>
  </details>
</template>

<style scoped>
.iev { margin-top: var(--sp-3); border-top: 1px dashed var(--border-strong); padding-top: var(--sp-2); font-size: var(--fs-xs); color: var(--text-2); }
summary { cursor: pointer; color: var(--text-3); }
ul { list-style: none; margin: var(--sp-2) 0 0; padding: 0; display: grid; gap: var(--sp-3); }
.head { gap: var(--sp-2); align-items: center; }
.ref { font-size: 11px; }
.txt { margin: var(--sp-1) 0 0; color: var(--text); line-height: 1.6; white-space: pre-wrap; }
.quote { margin: var(--sp-1) 0 0; line-height: 1.6; border-left: 2px solid var(--border-strong); padding-left: var(--sp-2); }
.detail { margin: var(--sp-1) 0 0; line-height: 1.6; white-space: pre-wrap; }
.err { color: var(--neg); margin: var(--sp-1) 0 0; }
.small { margin: var(--sp-2) 0 0; }
.shots { display: flex; gap: var(--sp-2); margin-top: var(--sp-2); }
.shots img { height: 72px; width: auto; border: 1px solid var(--border); border-radius: var(--r-sm); display: block; }
</style>
