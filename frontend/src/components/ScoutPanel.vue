<script setup>
// 运行前审核：侦察员核对说明书与真实网站的结果。只给审核者看，不会告诉人物。
import { ref, computed } from 'vue'
import { AlertTriangle } from 'lucide-vue-next'

const props = defineProps({ scout: { type: Object, default: null } })
const VERDICT = { consistent: '一致', inconsistent: '不一致', unverified: '未核对' }
const showAll = ref(false)
const checks = computed(() => props.scout?.checks ?? [])
const counts = computed(() => Object.fromEntries(Object.keys(VERDICT).map((v) => [v, checks.value.filter((c) => c.verdict === v).length])))
const rows = computed(() => checks.value.filter((c) => showAll.value || c.verdict === 'inconsistent'))
// 所有行的原因相同时只展示一次，页面原文和截图仍各自保留。
const commonReason = computed(() => {
  const reason = checks.value[0]?.observed
  return reason && checks.value.every((c) => c.observed === reason) ? reason : ''
})
const showObserved = computed(() => !commonReason.value || checks.value.some((c) => c.observed_quote))
</script>

<template>
  <section v-if="scout && scout.status !== 'pending'" class="panel scout">
    <div class="panel-head"><h3>侦察结果</h3><span class="aside faint">用一个浏览会话核对说明书与真实网站；结果不会告诉人物</span></div>
    <p v-if="scout.status === 'skipped'" class="faint">没有侦察：{{ scout.reason }}。</p>
    <template v-else>
      <p class="scout-summary">一致 {{ counts.consistent }} · <b>不一致 {{ counts.inconsistent }}</b> · 未核对 {{ counts.unverified }}</p>
      <p v-if="commonReason" class="shared-reason">{{ commonReason }}</p>
      <div v-if="scout.status === 'failed'" class="warn" role="status"><AlertTriangle /><div>侦察没有完成<template v-if="scout.reason && scout.reason !== commonReason">（{{ scout.reason }}）</template>，下列说法都未核对。不影响生成人物与模拟。</div></div>
      <div v-if="rows.length" class="table-wrap">
        <table class="data">
          <thead><tr><th>说法</th><th>来源</th><th>写的</th><th>结论</th><th v-if="showObserved">看到的</th><th>截图</th></tr></thead>
          <tbody>
            <tr v-for="c in rows" :key="c.claim_id">
              <td><b>{{ c.area }}</b></td><td class="faint">{{ c.source }}</td><td class="wrap muted">{{ c.says }}</td>
              <td :class="{ bad: c.verdict === 'inconsistent' }">{{ VERDICT[c.verdict] }}</td>
              <td v-if="showObserved" class="wrap"><template v-if="!commonReason">{{ c.observed }}</template><span v-if="c.observed_quote" class="faint">（页面原文：“{{ c.observed_quote }}”）</span></td>
              <td><a v-for="(u, i) in c.screenshots" :key="u" :href="u" target="_blank" rel="noopener">截图 {{ i + 1 }} </a><span v-if="!c.screenshots.length" class="faint">—</span></td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="foot">
        <p v-if="rows.length" class="faint small">只以访客身份核对，需要登录的部分未核对；“主 Agent 归纳”的说法不是说明书原文。要修正说明书，请修改后新建运行；也可以照常批准，人物会在体验中自己遇到这些情况。</p>
        <button v-if="checks.length > counts.inconsistent" class="btn btn-ghost sm" type="button" :aria-expanded="showAll" @click="showAll = !showAll">{{ showAll ? '收起' : `查看全部 ${checks.length} 条` }}</button>
      </div>
    </template>
  </section>
</template>

<style scoped>
.scout { margin-bottom: 16px; }
.scout-summary { margin: 0 0 var(--sp-2); font-size: var(--fs-sm); }
.shared-reason { margin: 0 0 var(--sp-2); color: var(--text-2); font-size: var(--fs-sm); overflow-wrap: anywhere; }
.scout td.wrap { white-space: normal; min-width: 180px; padding-top: 8px; padding-bottom: 8px; }
.scout td.bad { color: var(--sev-2); font-weight: 600; }
.scout td a { margin-right: 6px; }
.foot { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 16px; margin-top: 8px; }
</style>
