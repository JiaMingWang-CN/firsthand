<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { findings, posts, withheld, surveys, inconsistencies, scout, run, personas, steps, reads } from '../lib/data.js'
import { TEXT_ONLY_NOTE, P, clockOf, flowStats, npsOf, issueCount, priorityScore } from '../lib/sim.js'
import { drawers, openDrawer } from '../lib/store.js'
import { Info, AlertTriangle } from 'lucide-vue-next'
import FindingCard from '../components/FindingCard.vue'
import DotMatrix from '../components/DotMatrix.vue'
import PersonaChip from '../components/PersonaChip.vue'
import VoiceCard from '../components/VoiceCard.vue'
import SevTag from '../components/SevTag.vue'
import NpsChart from '../components/NpsChart.vue'
import InfluenceGraph from '../components/InfluenceGraph.vue'
import EmotionCurve from '../components/EmotionCurve.vue'
import StatusDot from '../components/StatusDot.vue'
import PageIntro from '../components/PageIntro.vue'

const report = computed(() => run.report)
const fileUrl = (path) => `/api/runs/${encodeURIComponent(run.id)}/files/${path.split('/').map(encodeURIComponent).join('/')}`
const issues = computed(() => findings.filter((f) => f.kind === 'issue').sort((a, b) => priorityScore(b) - priorityScore(a)))
const highlights = computed(() => findings.filter((f) => f.kind === 'highlight'))
const sevFilter = ref('all')
const shownIssues = computed(() => issues.value.filter((f) =>
  sevFilter.value === 'all' ? true : sevFilter.value === '34' ? f.sev >= 3 : f.sev === Number(sevFilter.value)))

const done = computed(() => personas.filter((p) => p.outcome === 'success'))
const nps = computed(() => npsOf(Object.values(surveys).map((s) => s.nps).filter(Number.isInteger)))
const scored = computed(() => Object.values(surveys).filter((s) => Number.isInteger(s.nps)).length)
const flowsS = computed(() => flowStats().filter((f) => f.people.length))
const explorers = computed(() => personas.filter((p) => p.assignment === 'explore'))
const unsaidLurkers = computed(() => withheld.filter((w) => w.lurker).length)
const unsaidSpeakers = computed(() => withheld.length - unsaidLurkers.value)
const alsoPublic = computed(() => withheld.filter((w) => w.alsoPublic).length)
const topSev = computed(() => issueCount(1) + issueCount(2))
const SOURCE = { agent_self_report: 'Agent 自述', runtime_limit: '运行时限制', infrastructure: '基础设施' }
const outcomeSources = computed(() => Object.entries(report.value?.overview?.outcome_sources ?? {}).map(([k, n]) => `${SOURCE[k] ?? k} ${n}`).join('、'))
const coverage = computed(() => report.value?.overview?.coverage_notes ?? [])

// —— 沉默信号：按人物汇总 ——
const silence = computed(() => personas.map((p) => {
  const mine = withheld.filter((w) => w.pid === p.id)
  return { pid: p.id, n: mine.length, pains: mine.filter((w) => w.kind === 'pain').length, also: mine.filter((w) => w.alsoPublic).length }
}).filter((s) => s.n).sort((a, b) => b.n - a.n))
const maxSilence = computed(() => Math.max(1, ...silence.value.map((s) => s.n)))
const privateVoices = computed(() => personas.map((p) => ({ pid: p.id, s: surveys[p.id] })).filter((x) => x.s?.hasExperience)
  .sort((a, b) => Number(b.s.unspoken !== '没有。') - Number(a.s.unspoken !== '没有。')).slice(0, 6))

// —— 舆论动态 ——
const beforeReaders = computed(() => new Set(reads.filter((r) => r.before).map((r) => r.pid)).size)
const changed = computed(() => Object.values(surveys).filter((s) => s.changedByAll?.length).length)

// —— 分时段（按人物本地时刻） ——
const avg = (pid) => (steps[pid]?.length ? steps[pid].reduce((s, x) => s + x.sat, 0) / steps[pid].length : null)
const bands = computed(() => [
  { name: '深夜', range: '23:00–06:00', test: (m) => m >= 1380 || m < 360 },
  { name: '早晨', range: '06:00–11:00', test: (m) => m >= 360 && m < 660 },
  { name: '午间', range: '11:00–14:00', test: (m) => m >= 660 && m < 840 },
  { name: '下午', range: '14:00–18:00', test: (m) => m >= 840 && m < 1080 },
  { name: '晚间', range: '18:00–23:00', test: (m) => m >= 1080 && m < 1380 },
].map((b) => {
  const ps = personas.filter((p) => p.localSlot != null && b.test(p.localSlot))
  const avgs = ps.map((p) => avg(p.id)).filter((v) => v != null)
  return { ...b, ps, done: ps.filter((p) => p.outcome === 'success').length, avg: avgs.length ? avgs.reduce((s, v) => s + v, 0) / avgs.length : null }
}))
const scatter = computed(() => personas.filter((p) => p.localSlot != null && avg(p.id) != null).map((p) => ({ p, x: p.localSlot, y: avg(p.id), n: steps[p.id].length })))
const extremes = computed(() => {
  const list = [...scatter.value].sort((a, b) => a.y - b.y)
  return list.length >= 2 ? [list[0].p, list[list.length - 1].p] : []
})

// —— J / K 在问题之间切换 ——
const active = ref(-1)
function onKey(e) {
  if (drawers.stack.length || e.target.closest('input, textarea')) return
  const list = shownIssues.value
  if (!list.length) return
  if (e.key === 'j' || e.key === 'J') active.value = Math.min(list.length - 1, active.value + 1)
  else if (e.key === 'k' || e.key === 'K') active.value = Math.max(0, active.value - 1)
  else if (e.key === 'Enter' && !e.target.closest('button, a, summary, select, [role="button"]') && active.value >= 0) return openDrawer({ type: 'finding', id: list[active.value].id })
  else return
  document.getElementById(list[active.value].id)?.scrollIntoView({ block: 'center', behavior: 'smooth' })
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

const toc = [
  ['ov', '总览'], ['issues', '问题清单'], ['highlights', '亮点'], ['voices', '公开声音与沉默信号'],
  ['dynamics', '舆论动态'], ['timeofday', '分时段体验差异'], ['scout', '说明书与实际不一致'], ['about', '关于这份报告'],
]
const scrollTo = (id) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
const sx = (m) => 36 + (m / 1440) * 424
const sy = (v) => 20 + ((1 - v) / 2) * 160
</script>

<template>
  <div class="page report">
    <header class="page-head">
      <div>
        <div class="eyebrow">报告</div>
        <h1 class="page-title">{{ run.title }}报告</h1>
        <PageIntro>{{ personas.length }} 名模拟人物按各自作息在 {{ run.simDays }} 天的模拟时间线上真实使用了产品，并在社区中讨论。每条结论都附证据，三次点击内可到达截图、步骤和回放。</PageIntro>
        <span v-if="run.textOnly" class="tag neg" :title="TEXT_ONLY_NOTE"><span class="dot"></span>参考性有限 · 纯文本模型</span>
      </div>
    </header>

    <div v-if="run.textOnly" class="warn nr" role="status"><AlertTriangle /><div><b>{{ TEXT_ONLY_NOTE }}。</b>排版、图片、颜色这类视觉问题不在下面的结论里；录像和截图照常保存，可回放核对。</div></div>
    <div v-if="!report" class="note nr"><Info /><div><b>这次运行还没有阶段 5 报告</b>：下面的问题清单与亮点为空；人物、社区和体验记录可以在左侧其他页面查看。</div></div>
    <div v-else-if="!report.result?.passed" class="note nr"><Info /><div><b>这份报告没有通过验收</b>：{{ (report.result?.errors ?? []).join('；') || '请查看阶段 5 的结果文件。' }}</div></div>

    <div class="layout">
      <div class="content">
        <!-- 01 总览 -->
        <section id="ov" class="section first">
          <div class="section-head"><span class="n">01</span><h2>总览</h2><span class="aside">来源：体验记录 · 离场问卷 · {{ personas.length }} 名人物</span></div>
          <p class="conclusion">
            <b class="num">{{ done.length }}/{{ personas.length }}</b> 名人物自述完成了体验。
            问题清单 <b class="num">{{ issues.length }}</b> 条<template v-if="issues.length">，其中 <b class="num">{{ topSev }}</b> 条为 S1/S2</template>；
            另有 <b class="num">{{ withheld.length }}</b> 条体验没有在社区说出，其中 <b class="num">{{ unsaidLurkers }}</b> 条来自潜水者。
          </p>
          <div class="grid g3 kpis">
            <div class="panel tight kpi">
              <div class="k">体验完成</div>
              <div class="v big">{{ done.length }}<small>/{{ personas.length }}</small></div>
              <DotMatrix :x="done.length" :y="personas.length" :show-text="false" />
              <div class="d">自由探索 {{ explorers.length }} 人</div>
            </div>
            <div class="panel tight kpi">
              <div class="k">推荐意愿 NPS</div>
              <div class="v big">{{ nps.score ?? '—' }}</div>
              <div class="d num" :title="`样本仅 ${scored} 人，仅作方向参考`">推荐 {{ nps.promoters }} · 被动 {{ nps.passives }} · 贬损 {{ nps.detractors }}</div>
            </div>
            <div class="panel tight kpi">
              <div class="k">问题</div>
              <div class="sevs">
                <span v-for="s in [1, 2, 3, 4]" :key="s" class="sv"><SevTag :sev="s" /><b class="num">{{ issueCount(s) }}</b></span>
              </div>
              <div class="d">亮点 {{ highlights.length }} 条</div>
            </div>
          </div>

          <div class="ovgrid">
          <div class="panel flush flows" v-if="flowsS.length">
            <div class="table-wrap">
              <table class="data">
                <thead><tr><th>关键流程</th><th>负责人物</th><th>完成</th><th class="r">平均步数</th><th>结果</th></tr></thead>
                <tbody>
                  <tr v-for="f in flowsS" :key="f.id" @click="openDrawer({ type: 'persona', pid: (f.people.find((p) => p.outcome !== 'success') || f.people[0]).id })">
                    <td><b>{{ f.name }}</b> <span class="faint num">{{ f.id }}</span></td>
                    <td><span class="row"><PersonaChip v-for="p in f.people" :key="p.id" :pid="p.id" /></span></td>
                    <td><DotMatrix :x="f.done.length" :y="f.people.length" /></td>
                    <td class="r num">{{ (f.people.reduce((s, p) => s + steps[p.id].length, 0) / f.people.length).toFixed(1) }}</td>
                    <td><span class="row"><StatusDot v-for="p in f.people" :key="p.id" :status="p.outcome === 'quit' ? 'quit' : p.outcome === 'error' ? 'err' : 'done'" /></span></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <details class="panel tight nps-distribution">
            <summary>查看推荐意愿分布</summary>
            <NpsChart />
          </details>
          </div>
        </section>

        <!-- 02 问题清单 -->
        <section id="issues" class="section">
          <div class="section-head">
            <span class="n">02</span><h2>问题清单</h2>
            <span class="aside" title="按「影响人数 × 严重度 × 证据强度」排序，不按点赞数 · J K 切换 Enter 打开">按影响 × 严重度 × 证据排序</span>
          </div>
          <div class="seg filt" role="group" aria-label="按严重度筛选">
            <button type="button" :aria-pressed="sevFilter === 'all'" @click="sevFilter = 'all'">全部 {{ issues.length }}</button>
            <button type="button" :aria-pressed="sevFilter === '1'" @click="sevFilter = '1'">S1 致命 {{ issueCount(1) }}</button>
            <button type="button" :aria-pressed="sevFilter === '2'" @click="sevFilter = '2'">S2 严重 {{ issueCount(2) }}</button>
            <button type="button" :aria-pressed="sevFilter === '34'" @click="sevFilter = '34'">S3–S4 {{ issueCount(3) + issueCount(4) }}</button>
          </div>
          <div class="flist">
            <FindingCard v-for="(f, i) in shownIssues" :key="f.id" :f="f" :rank="i + 1" :active="active === i" />
            <p v-if="!shownIssues.length" class="faint">{{ report ? '没有符合条件的问题。' : '没有报告，所以没有问题清单。' }}</p>
          </div>
        </section>

        <!-- 03 亮点 -->
        <section id="highlights" class="section">
          <div class="section-head"><span class="n">03</span><h2>亮点</h2></div>
          <div class="grid g3">
            <FindingCard v-for="f in highlights" :key="f.id" :f="f" />
          </div>
          <p v-if="!highlights.length" class="faint">没有亮点记录。</p>
        </section>

        <!-- 04 公开声音与沉默信号 -->
        <section id="voices" class="section">
          <div class="section-head"><span class="n">04</span><h2>公开声音与沉默信号</h2></div>
          <p class="silence-summary" :title="report?.silence ? `来自 ${report.silence.length} 次表达决定（同一体验可能被多次隐瞒）` : '无报告，按表达过滤记录推出'">{{ withheld.length }} 条体验没有在社区说出 · 发言者 {{ unsaidSpeakers }} · 潜水者 {{ unsaidLurkers }}</p>
          <p class="lead">社区里说出的、体验了但没说的、私下问卷，是三种不同的信息。<template v-if="alsoPublic">有 {{ alsoPublic }} 条未说出的体验本人在别处公开过。</template></p>

          <div class="grid g3 vcols">
            <div>
              <div class="vh"><span class="tag public">说出的</span><span class="faint num">{{ posts.length }} 帖 · {{ posts.reduce((s, p) => s + p.comments.length, 0) }} 评论</span></div>
              <div class="vstack">
                <VoiceCard v-for="p in posts.slice(0, 8)" :key="p.id" kind="public" :pid="p.author" :t="p.t" action="发帖" :text="p.title" :evidence="p.evidence.slice(0, 1)" />
                <p v-if="posts.length > 8" class="faint more">还有 {{ posts.length - 8 }} 帖，见「社区」页。</p>
              </div>
            </div>
            <div>
              <div class="vh"><span class="tag withheld">未说出的</span><span class="faint num">{{ withheld.length }} 条</span></div>
              <div class="vstack">
                <VoiceCard v-for="(w, i) in withheld.slice(0, 10)" :key="i" kind="withheld" :pid="w.pid" :t="w.t" :text="w.item" :reason="w.reason" :evidence="w.evidence.slice(0, 1)" />
                <p v-if="withheld.length > 10" class="faint more">还有 {{ withheld.length - 10 }} 条，见各人物档案。</p>
              </div>
            </div>
            <div>
              <div class="vh"><span class="tag private">私下 · 问卷</span><span class="faint num">{{ Object.keys(surveys).length }}/{{ personas.length }} 作答</span></div>
              <div class="vstack">
                <VoiceCard v-for="x in privateVoices" :key="x.pid" kind="private" :pid="x.pid" :text="x.s.unspoken !== '没有。' ? x.s.unspoken : x.s.worst" :extra="x.s.nps == null ? undefined : `NPS ${x.s.nps}`" />
              </div>
            </div>
          </div>

          <h3 class="sub">各人物没有说出的体验</h3>
          <div class="panel tight" v-if="silence.length">
            <div v-for="s in silence" :key="s.pid" class="trow" role="button" tabindex="0" @click="openDrawer({ type: 'persona', pid: s.pid, tab: 'unsaid' })" @keydown.enter="openDrawer({ type: 'persona', pid: s.pid, tab: 'unsaid' })">
              <span class="tk"><PersonaChip :pid="s.pid" /><span v-if="P[s.pid].participation === 'lurker'" class="tag withheld only">潜水者</span></span>
              <span class="barw"><i class="pri" :style="{ width: (s.n / maxSilence) * 100 + '%' }"></i></span>
              <span class="num tn">{{ s.n }}<span v-if="s.pains" class="faint"> · 痛点 {{ s.pains }}</span><span v-if="s.also" class="faint"> · 别处公开过 {{ s.also }}</span></span>
            </div>
          </div>
          <p v-else class="faint">没有未说出的体验记录。</p>

          <h3 class="sub">需要复核的说法 · {{ inconsistencies.length }}</h3>
          <div class="incons">
            <div v-for="x in inconsistencies" :key="x.pid" class="inc">
              <div class="who"><PersonaChip :pid="x.pid" /></div>
              <div class="voice public"><div class="who2 faint">公开</div>{{ x.public }}</div>
              <div class="voice private"><div class="who2 kind">复核提示</div>{{ x.private }}</div>
              <div class="evc"><button class="btn btn-ghost sm" type="button" @click="openDrawer({ type: 'persona', pid: x.pid, tab: 'unsaid' })">查看问卷与未说出的</button></div>
            </div>
            <p v-if="!inconsistencies.length" class="faint">问卷与公开发言之间没有被标记需要复核的地方。</p>
          </div>
        </section>

        <!-- 05 舆论动态 -->
        <section id="dynamics" class="section">
          <div class="section-head"><span class="n">05</span><h2>舆论动态</h2></div>
          <p class="lead">{{ beforeReaders }} 名人物在自己体验之前就读到了帖子，从而形成预期；{{ changed }} 名人物在问卷里自述自己的观点被讨论改变。帖子按触达量而不是点赞排序。</p>
          <div class="panel"><InfluenceGraph /></div>
        </section>

        <!-- 06 分时段 -->
        <section id="timeofday" class="section">
          <div class="section-head"><span class="n">06</span><h2>分时段体验差异</h2></div>
          <div class="grid g2">
            <div class="panel">
              <div class="label">各人物体验时刻（本地）与平均满意度</div>
              <svg viewBox="0 0 480 214" width="100%" role="img" aria-label="散点图：横轴为体验开始的本地时刻，纵轴为该人物全程平均满意度。">
                <rect :x="sx(0)" y="20" :width="sx(360) - sx(0)" height="160" fill="var(--surface-2)" />
                <rect :x="sx(1380)" y="20" :width="sx(1440) - sx(1380)" height="160" fill="var(--surface-2)" />
                <line :x1="sx(0)" :x2="sx(1440)" :y1="sy(0)" :y2="sy(0)" stroke="var(--border-strong)" stroke-dasharray="3 3" />
                <text x="0" :y="sy(1) + 4" class="ax">满意</text><text x="0" :y="sy(0) + 4" class="ax">0</text><text x="0" :y="sy(-1) + 4" class="ax">受挫</text>
                <text v-for="h in [0, 6, 12, 18, 24]" :key="h" :x="sx(h * 60)" y="202" class="ax mid">{{ String(h).padStart(2, '0') }}:00</text>
                <g v-for="d in scatter" :key="d.p.id" class="sp" tabindex="0" role="button" :aria-label="`${d.p.realname}：本地 ${clockOf(d.x)} 体验，平均满意度 ${d.y.toFixed(2)}`"
                   @click="openDrawer({ type: 'persona', pid: d.p.id })" @keydown.enter="openDrawer({ type: 'persona', pid: d.p.id })">
                  <circle :cx="sx(d.x)" :cy="sy(d.y)" :r="4 + d.n / 3" :fill="d.p.color" opacity=".85" stroke="var(--surface)" stroke-width="1.5" />
                  <text :x="sx(d.x)" :y="sy(d.y) - 9 - d.n / 3" class="lb">{{ d.p.realname }}</text>
                </g>
              </svg>
              <div class="source">来源：体验记录 · 点的大小为步数 · 阴影为夜间（本地 23:00–06:00）</div>
            </div>
            <div class="panel flush">
              <table class="data">
                <thead><tr><th>时段（本地）</th><th>人物</th><th>完成</th><th class="r">平均满意度</th></tr></thead>
                <tbody>
                  <tr v-for="b in bands" :key="b.name" @click="b.ps[0] && openDrawer({ type: 'persona', pid: b.ps[0].id })">
                    <td><b>{{ b.name }}</b> <span class="num faint">{{ b.range }}</span></td>
                    <td><span class="row"><PersonaChip v-for="p in b.ps" :key="p.id" :pid="p.id" /><span v-if="!b.ps.length" class="faint">—</span></span></td>
                    <td><DotMatrix v-if="b.ps.length" :x="b.done" :y="b.ps.length" /><span v-else class="faint">—</span></td>
                    <td class="r num" :style="{ color: b.avg != null && b.avg < 0 ? 'var(--neg)' : 'var(--text)' }">{{ b.avg == null ? '—' : (b.avg > 0 ? '+' : '') + b.avg.toFixed(2) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <div class="grid g2 pair" v-if="extremes.length">
            <div class="panel tight"><EmotionCurve :pids="[extremes[0].id]" :title="`平均满意度最低 · ${extremes[0].realname} · 本地 ${clockOf(extremes[0].localSlot)}`" :height="130" /></div>
            <div class="panel tight"><EmotionCurve :pids="[extremes[1].id]" :title="`平均满意度最高 · ${extremes[1].realname} · 本地 ${clockOf(extremes[1].localSlot)}`" :height="130" /></div>
          </div>
        </section>

        <!-- 07 侦察 -->
        <section id="scout" class="section">
          <div class="section-head"><span class="n">07</span><h2>说明书与实际不一致</h2><span class="aside">来源：侦察</span></div>
          <div class="panel flush" v-if="scout.length">
            <div class="table-wrap">
              <table class="data">
                <thead><tr><th>位置</th><th>来源</th><th>使用说明写的</th><th>侦察看到的</th><th>截图</th></tr></thead>
                <tbody>
                  <tr v-for="(s, i) in scout" :key="s.id ?? i">
                    <td><b>{{ s.area ?? s.id }}</b></td><td class="faint">{{ s.source ?? '说明书' }}</td><td class="wrap muted">{{ s.manual }}</td>
                    <td class="wrap">{{ s.actual }}<span v-if="s.quote" class="faint">（页面原文：“{{ s.quote }}”）</span></td>
                    <td><a v-for="(path, j) in s.screenshots ?? []" :key="path" :href="fileUrl(path)" target="_blank" rel="noopener">截图 {{ j + 1 }} </a><span v-if="!s.screenshots?.length" class="faint">—</span></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <div class="note"><Info /><div>{{ report?.scout?.note ?? 'Scout 未执行，没有说明书与实际产品不一致的记录。' }}
            <template v-if="report?.scout?.unverified?.length"> 未核对：{{ report.scout.unverified.map((u) => `${u.area}（${u.reason}）`).join('；') }}。</template></div></div>
        </section>

        <!-- 方法说明集中在文末，按需展开 -->
        <details id="about" class="section panel about">
          <summary>关于这份报告</summary>
          <p v-if="outcomeSources" class="faint src-note">任务成败的判定来源：{{ outcomeSources }}。</p>
          <div class="note cov" v-if="coverage.length || run.limitations?.length">
            <Info />
            <div>
              <b>覆盖说明与限制</b>
              <ul class="covl">
                <li v-for="(c, i) in coverage" :key="'c' + i">{{ c }}</li>
                <li v-for="(l, i) in run.limitations" :key="'l' + i" class="faint">{{ l }}</li>
              </ul>
            </div>
          </div>
          <p class="faint">舆论动态中的观点变化来自人物自述，不是因果结论。</p>
          <p class="faint">分时段体验按人物本地时刻的体验开始时间分段。样本很小，且时段与人设混杂，只能作为线索。</p>
          <dl class="run-meta">
            <template v-if="run.startedAt || run.endedAt"><dt>起止时间</dt><dd>{{ run.startedAt ? new Date(run.startedAt).toLocaleString('zh-CN', { hour12: false }) : '—' }} → {{ run.endedAt ? new Date(run.endedAt).toLocaleString('zh-CN', { hour12: false }) : '—' }}</dd></template>
            <template v-if="run.model"><dt>模型</dt><dd>{{ run.model }}</dd></template>
          </dl>
        </details>
      </div>

      <aside class="toc" aria-label="报告目录">
        <div class="label">目录</div>
        <a v-for="([id, name], i) in toc" :key="id" :href="`#${id}`" @click.prevent="scrollTo(id)">
          <span class="num">{{ String(i + 1).padStart(2, '0') }}</span>{{ name }}
        </a>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.nr { margin-bottom: var(--sp-4); }
.layout { display: grid; grid-template-columns: minmax(0, 1fr) 180px; gap: var(--sp-6); }
.content { min-width: 0; }
.section.first { margin-top: 0; }
.toc { position: sticky; top: 84px; align-self: start; display: flex; flex-direction: column; gap: 2px; font-size: var(--fs-sm); }
.toc .label { margin-bottom: var(--sp-2); }
.toc a { color: var(--text-2); padding: 4px 0; display: flex; gap: var(--sp-2); text-decoration: none; }
.toc a:hover { color: var(--text); }
.toc .num { color: var(--text-3); font-size: var(--fs-xs); padding-top: 2px; }
.conclusion { font-size: var(--fs-lg); line-height: 1.7; margin: 0 0 var(--sp-3); max-width: 860px; }
.src-note { font-size: var(--fs-xs); margin: var(--sp-3) 0; }
.kpis { margin-bottom: var(--sp-4); }
.sevs { display: grid; grid-template-columns: 1fr 1fr; gap: 6px var(--sp-3); margin: var(--sp-2) 0; }
.sv { display: flex; align-items: center; justify-content: space-between; gap: var(--sp-2); }
.sv b { font-size: var(--fs-lg); }
.ovgrid { display: grid; gap: var(--sp-3); }
summary { cursor: pointer; color: var(--text-2); font-size: var(--fs-sm); }
summary:hover { color: var(--text); }
.nps-distribution[open] summary { margin-bottom: var(--sp-3); }
.about { scroll-margin-top: 80px; padding-top: var(--sp-3); border-top: 1px solid var(--ink); font-size: var(--fs-sm); overflow-wrap: anywhere; }
.about summary { font-weight: 600; }
.about .cov { margin-top: var(--sp-3); }
.run-meta { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: var(--sp-2) var(--sp-3); }
.run-meta dt { color: var(--text-3); }
.run-meta dd { margin: 0; }
.silence-summary { margin: 0 0 var(--sp-3); font-size: var(--fs-sm); color: var(--text-2); }
.cov { font-size: var(--fs-xs); }
.covl { margin: var(--sp-1) 0 0; padding-left: 1.2em; line-height: 1.7; }
.flows .row { flex-wrap: nowrap; }
.filt { display: flex; flex-wrap: wrap; width: fit-content; max-width: 100%; margin-bottom: var(--sp-4); }
.flist { display: grid; gap: var(--sp-3); }
.vcols { align-items: start; }
.vh { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--sp-3); font-size: var(--fs-xs); }
.vstack { display: grid; gap: var(--sp-2); }
.more { margin: 0; font-size: var(--fs-xs); }
.sub { font-size: var(--fs-lg); margin: var(--sp-6) 0 var(--sp-3); }
.trow { display: grid; grid-template-columns: 200px 1fr minmax(24px, auto); gap: var(--sp-3); align-items: center; height: 32px; font-size: var(--fs-sm); cursor: pointer; }
.tk { display: flex; align-items: center; gap: 6px; white-space: nowrap; }
.only { height: 18px; font-size: 11px; }
.barw { height: 8px; background: var(--surface-2); border-radius: 0; overflow: hidden; }
.barw i { display: block; height: 100%; border-radius: 0; }
.barw .pri { background: var(--vis-private); }
.tn { text-align: right; color: var(--text-2); white-space: nowrap; }
.incons { display: grid; gap: var(--sp-2); }
.inc { display: grid; grid-template-columns: 120px 1fr 1fr auto; gap: var(--sp-3); align-items: center; }
.who2 { font-size: var(--fs-xs); font-weight: 700; margin-bottom: 2px; }
.voice.private .kind { color: var(--vis-private); }
.evc { display: flex; gap: 4px; }
.ax { font-size: 10px; fill: var(--text-3); font-family: var(--font-mono); }
.ax.mid { text-anchor: middle; }
.lb { font-size: 10px; fill: var(--text-2); text-anchor: middle; }
.sp { cursor: pointer; outline: none; }
.sp:hover circle, .sp:focus-visible circle { stroke: var(--text); }
.pair { margin-top: var(--sp-4); }
.wrap { white-space: normal; min-width: 180px; }
@media (max-width: 1439px) { .layout { grid-template-columns: 1fr; } .toc { display: none; } }
@media (max-width: 959px) {
  .inc { grid-template-columns: 1fr; }
  .trow { grid-template-columns: 130px 1fr auto; }
}
@media (max-width: 640px) {
  .trow { grid-template-columns: 1fr; height: auto; gap: var(--sp-1); padding: var(--sp-2) 0; }
  .tk { flex-wrap: wrap; white-space: normal; }
  .tn { text-align: left; white-space: normal; }
}
</style>
