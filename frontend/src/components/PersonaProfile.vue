<script setup>
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { steps, surveys, reads, posts, reactions } from '../lib/data.js'
import { P, label, fmt, assignmentLabel, withheldFor, postById } from '../lib/sim.js'
import { openDrawer, closeAllDrawers } from '../lib/store.js'
import { Mic } from 'lucide-vue-next'
import PersonaCard from './PersonaCard.vue'
import EmotionCurve from './EmotionCurve.vue'
import VoiceCard from './VoiceCard.vue'
import StatusDot from './StatusDot.vue'
import SimTime from './SimTime.vue'

const props = defineProps({ pid: String, tab: String })
const router = useRouter()
const route = useRoute()
const p = computed(() => P[props.pid])
const tab = ref(props.tab || 'record')
const sv = computed(() => surveys[props.pid])
const myReads = computed(() => reads.filter((r) => r.pid === props.pid).sort((a, b) => a.t - b.t))
// 体验前每次刷社区都可能再看到同一条帖子：预期按帖子合并（后端给模型的预期同样按帖子去重），列出每次看到的时刻
const expectations = computed(() => {
  const byPost = new Map()
  for (const r of myReads.value.filter((x) => x.before && x.expectation)) {
    if (!byPost.has(r.post)) byPost.set(r.post, { ...r, times: [] })
    const item = byPost.get(r.post)
    item.times.push(r.t)
    if (r.verdict === 'confirmed') item.verdict = 'confirmed'
  }
  return [...byPost.values()]
})
const myPosts = computed(() => posts.filter((x) => x.author === props.pid))
const myComments = computed(() => posts.flatMap((x) => x.comments.filter((c) => c.author === props.pid).map((c) => ({ ...c, post: x }))))
const myReacts = computed(() => reactions.filter((r) => r.pid === props.pid))
const wh = computed(() => withheldFor(props.pid))
const bigFive = { O: '开放性', C: '尽责性', E: '外向性', A: '宜人性', N: '神经质' }
const lvl = { 低: 1, 中: 2, 高: 3 }
const targetName = (id) => postById[id]?.title || posts.flatMap((x) => x.comments).find((c) => c.id === id)?.body.slice(0, 18) + '…'

function interview() { closeAllDrawers(); router.push({ name: 'interview', params: { runId: route.params.runId }, query: { pid: props.pid } }) }
</script>

<template>
  <div>
    <PersonaCard :pid="pid" />
    <div class="row actions">
      <StatusDot :status="p.outcome === 'quit' ? 'quit' : p.outcome === 'error' ? 'err' : 'done'" />
      <span class="faint oc">{{ p.outcomeReason }}</span>
    </div>
    <button class="btn btn-secondary sm" type="button" @click="interview"><Mic />采访 {{ p.realname }}</button>

    <div class="tabs" role="tablist" style="margin-top: var(--sp-5)">
      <button role="tab" :aria-selected="tab === 'record'" @click="tab = 'record'">体验记录<span class="count">{{ steps[pid].length }}</span></button>
      <button role="tab" :aria-selected="tab === 'social'" @click="tab = 'social'">社区</button>
      <button role="tab" :aria-selected="tab === 'unsaid'" @click="tab = 'unsaid'">未说出的与问卷</button>
      <button role="tab" :aria-selected="tab === 'profile'" @click="tab = 'profile'">档案</button>
    </div>

    <!-- 体验记录 -->
    <div v-if="tab === 'record'">
      <dl class="kv">
        <dt>任务</dt><dd>{{ assignmentLabel(p) }}</dd>
        <dt>体验时</dt><dd><SimTime :m="p.slot" /> {{ p.state }}</dd>
        <dt>约束</dt><dd class="num">最多 {{ p.maxSteps }} 步 · 连续 {{ p.stall }} 步无进展即放弃</dd>
      </dl>
      <div v-for="r in expectations" :key="r.post" class="expect">
        <div class="label">体验前的预期 · 来自看帖<template v-if="r.times.length > 1"> · 看到 {{ r.times.length }} 次</template> <SimTime v-for="(t, i) in r.times" :key="i" :m="t" /></div>
        <p>{{ r.expectation }}</p>
        <span v-if="r.verdict === 'confirmed'" class="tag confused">体验后：预期被印证</span>
      </div>
      <div class="panel tight curve"><EmotionCurve :pids="[pid]" :title="`情绪曲线 · ${p.realname}`" /></div>
      <ol class="steps">
        <li v-for="(s, i) in steps[pid]" :key="i">
          <button type="button" @click="openDrawer({ type: 'evidence', ev: { pid, step: i + 1, kind: 'step' } }, { fromDrawer: true })">
            <span class="num sn">#{{ i + 1 }}</span>
            <span class="num st">{{ fmt(s.t).slice(3) }}</span>
            <span class="bar" :style="{ background: s.sat >= .3 ? 'var(--pos)' : s.sat <= -.3 ? 'var(--neg)' : 'var(--border-strong)' }"></span>
            <span class="a">{{ s.act }}<span v-if="s.trace.length" class="tr num">轨迹 {{ s.trace.length }}</span></span>
          </button>
        </li>
      </ol>
    </div>

    <!-- 社区 -->
    <div v-else-if="tab === 'social'" class="stack">
      <p class="faint small"><span class="part" :class="p.participation"><i></i>{{ label.participation[p.participation] }}</span> · 社区视图只显示说出的内容</p>
      <VoiceCard v-for="x in myPosts" :key="x.id" kind="public" :pid="pid" :t="x.t" action="发帖" :text="x.title" :evidence="x.evidence" />
      <VoiceCard v-for="c in myComments" :key="c.id" kind="public" :pid="pid" :t="c.t" action="评论" :text="c.body" :evidence="c.evidence" />
      <div v-if="myReacts.length" class="panel tight">
        <div class="label">点赞 {{ myReacts.length }} 次</div>
        <div v-for="r in myReacts" :key="r.target" class="li"><SimTime :m="r.t" /> 赞了「{{ targetName(r.target) }}」</div>
      </div>
      <div class="panel tight">
        <div class="label">看帖记录 {{ myReads.length }} 条</div>
        <div v-for="r in myReads" :key="r.post" class="li">
          <SimTime :m="r.t" />
          <button type="button" class="lnk" @click="openDrawer({ type: 'post', id: r.post }, { fromDrawer: true })">{{ postById[r.post]?.title }}</button>
          <span class="faint">{{ r.before ? '体验前' : '体验后' }}</span>
        </div>
        <p v-if="!myReads.length" class="faint small">没有看帖记录。</p>
      </div>
      <p v-if="!myPosts.length && !myComments.length" class="faint small">{{ p.realname }} 没有在社区发言。</p>
    </div>

    <!-- 未说出的与问卷 -->
    <div v-else-if="tab === 'unsaid'" class="stack">
      <VoiceCard v-for="(w, i) in wh" :key="i" kind="withheld" :pid="pid" :t="w.t" :text="w.item" :reason="w.reason" :evidence="w.evidence" />
      <p v-if="!wh.length" class="faint small">表达过滤中没有未说出的记录。</p>
      <p v-if="!sv" class="faint small">没有这个人物的离场问卷。</p>
      <template v-else>
      <VoiceCard kind="private" :pid="pid" :text="sv.unspoken" :extra="sv.nps == null ? undefined : `NPS ${sv.nps}`" :reason="sv.unspokenWhy" />
      <div class="panel tight">
        <div class="label">离场问卷（私下作答）</div>
        <dl class="kv">
          <dt>推荐意愿</dt><dd class="num">{{ sv.nps }} / 10</dd>
          <dt>继续使用</dt><dd>{{ sv.keep }}</dd>
          <dt>付费</dt><dd>{{ sv.pay }}</dd>
          <dt>最大的问题</dt><dd>{{ sv.worst }}</dd>
          <dt>最喜欢</dt><dd>{{ sv.best }}</dd>
          <dt>讨论的影响</dt><dd>{{ sv.changed }}</dd>
        </dl>
      </div>
      </template>
    </div>

    <!-- 档案 -->
    <div v-else class="stack">
      <dl class="kv">
        <dt>用户名</dt><dd class="num">@{{ p.username }}</dd>
        <dt>背景</dt><dd>{{ p.education }} · {{ p.industry }} · 收入{{ p.income }}</dd>
        <dt>相关经历</dt><dd>{{ p.history }}</dd>
        <dt>沟通风格</dt><dd>{{ p.mbti }} · {{ p.style }}</dd>
      </dl>
      <div class="panel tight">
        <div class="label">大五人格</div>
        <div v-for="(v, k) in p.bigFive" :key="k" class="b5">
          <span>{{ bigFive[k] }}</span>
          <span class="meter"><i v-for="n in 3" :key="n" :class="{ on: n <= lvl[v] }"></i></span>
          <span class="faint">{{ v }}</span>
        </div>
      </div>
      <div class="panel tight">
        <div class="label">浏览约束（由框架强制执行）</div>
        <dl class="kv">
          <dt>设备</dt><dd>{{ label.device[p.device] }} · {{ p.device === 'mobile' ? '390×844' : '1440×900' }}</dd>
          <dt>技术水平</dt><dd>{{ label.tech[p.tech] }}</dd>
          <dt>账号</dt><dd>{{ label.account[p.account] }}</dd>
          <dt>动机</dt><dd>{{ p.motivation }}</dd>
          <dt>额外工具</dt><dd class="num">{{ p.tools.length ? p.tools.join('、') : '无（看不到 Console / Network）' }}</dd>
        </dl>
      </div>
      <div class="panel tight">
        <div class="label">作息与表达</div>
        <dl class="kv">
          <dt>作息</dt><dd class="num">{{ p.wake }} 起床 · {{ p.sleep }} 睡觉</dd>
          <dt>坦率程度</dt><dd>{{ p.candor }}</dd>
          <dt>未说出倾向</dt><dd>{{ p.withhold }}<span v-if="p.withholdReasons.length" class="faint"> · {{ p.withholdReasons.join('；') }}</span></dd>
          <dt>体验日</dt><dd class="num">第 {{ p.browseDay }} 天</dd>
          <dt>采样参数</dt><dd class="num">{{ p.sampling ? `温度 ${p.sampling.temperature} · top_p ${p.sampling.top_p} · presence_penalty ${p.sampling.presence_penalty}` : '框架默认' }}</dd>
        </dl>
      </div>
    </div>
  </div>
</template>

<style scoped>
.actions { margin: var(--sp-4) 0 var(--sp-3); align-items: flex-start; flex-wrap: nowrap; }
.oc { font-size: var(--fs-xs); }
.kv { display: grid; grid-template-columns: 84px 1fr; gap: 6px var(--sp-3); margin: 0 0 var(--sp-3); font-size: var(--fs-sm); }
.kv dt { color: var(--text-3); font-size: var(--fs-xs); padding-top: 2px; }
.kv dd { margin: 0; }
.expect { background: var(--surface-2); border: 1px solid var(--border); border-left: 2px solid var(--sim); border-radius: var(--r-md); padding: var(--sp-3) var(--sp-4); margin-bottom: var(--sp-3); }
.expect .label { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px; }
.expect p { margin: 4px 0 6px; font-size: var(--fs-sm); }
.curve { margin-bottom: var(--sp-3); }
.steps { list-style: none; padding: 0; margin: 0; }
.steps button { width: 100%; display: flex; align-items: center; gap: var(--sp-2); padding: 6px var(--sp-2); border: none; background: none; text-align: left; border-radius: var(--r-sm); cursor: pointer; font-size: var(--fs-sm); }
.steps button:hover { background: var(--surface-2); }
.sn { width: 28px; color: var(--text-3); font-size: var(--fs-xs); }
.st { width: 40px; color: var(--sim); font-size: var(--fs-xs); }
.bar { width: 3px; height: 16px; border-radius: 2px; flex: none; }
.a { flex: 1; }
.tr { margin-left: 6px; font-size: 11px; color: var(--accent); background: var(--accent-soft); padding: 0 5px; border-radius: 3px; }
.stack { display: grid; gap: var(--sp-3); }
.small { font-size: var(--fs-xs); margin: 0; }
.li { display: flex; align-items: center; gap: var(--sp-2); font-size: var(--fs-sm); padding: 4px 0; flex-wrap: wrap; }
.lnk { background: none; border: none; color: var(--accent); cursor: pointer; padding: 0; text-align: left; font-size: var(--fs-sm); }
.lnk:hover { text-decoration: underline; }
.b5 { display: grid; grid-template-columns: 56px auto 1fr; gap: var(--sp-3); align-items: center; font-size: var(--fs-sm); padding: 2px 0; }
.meter { display: inline-flex; gap: 3px; }
.meter i { width: 22px; height: 6px; border-radius: 3px; background: var(--surface-2); display: block; }
.meter i.on { background: var(--text-2); }
</style>
