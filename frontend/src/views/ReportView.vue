<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { findings, posts, withheld, surveys, inconsistencies, scout, run, personas, steps } from '../mock/data.js'
import { P, fmt, flowStats, tasked, taskedDone, npsOf, priorityScore, issueCount, findingById } from '../lib/sim.js'
import { drawers, openDrawer, toast } from '../lib/store.js'
import { Info, Download, RotateCcw } from 'lucide-vue-next'
import FindingCard from '../components/FindingCard.vue'
import DotMatrix from '../components/DotMatrix.vue'
import PersonaChip from '../components/PersonaChip.vue'
import VoiceCard from '../components/VoiceCard.vue'
import EvTag from '../components/EvTag.vue'
import SevTag from '../components/SevTag.vue'
import NpsChart from '../components/NpsChart.vue'
import InfluenceGraph from '../components/InfluenceGraph.vue'
import EmotionCurve from '../components/EmotionCurve.vue'
import StatusDot from '../components/StatusDot.vue'

const router = useRouter()
const issues = computed(() => findings.filter((f) => f.kind === 'issue').sort((a, b) => priorityScore(b) - priorityScore(a)))
const highlights = findings.filter((f) => f.kind === 'highlight')
const sevFilter = ref('all')
const shownIssues = computed(() => issues.value.filter((f) =>
  sevFilter.value === 'all' ? true : sevFilter.value === '34' ? f.sev >= 3 : f.sev === Number(sevFilter.value)))
const nps = npsOf(Object.values(surveys).map((s) => s.nps))
const flowsS = flowStats()
const unsaidSpeakers = withheld.filter((w) => !w.lurker).length
const unsaidLurkers = withheld.filter((w) => w.lurker).length

// —— 公开讨论焦点 vs 私下最大问题（同结构，左右并排） ——
const topics = [
  { key: '注册回跳', public: ['post-1', 'post-2', 'c-2'], private: ['p2', 'p3'] },
  { key: '价格口径', public: ['post-3', 'c-4'], private: ['p6', 'p8'] },
  { key: '手机端按钮小', public: ['c-3'], private: ['p5'] },
  { key: '手机端找不到导出', public: [], private: ['p1'] },
  { key: '手机端无法拖拽字段', public: [], private: ['p10', 'p7'] },
  { key: '邀请成员报错', public: ['c-1'], private: ['p9'] },
]
const silentTopics = topics.filter((t) => t.public.length === 0)

// —— 分时段 ——
const avg = (pid) => steps[pid].reduce((s, x) => s + x.sat, 0) / steps[pid].length
const bands = [
  { name: '深夜', range: '23:00–06:00', test: (m) => m >= 1380 || m < 360 },
  { name: '早晨', range: '06:00–11:00', test: (m) => m >= 360 && m < 660 },
  { name: '午间', range: '11:00–14:00', test: (m) => m >= 660 && m < 840 },
  { name: '下午', range: '14:00–18:00', test: (m) => m >= 840 && m < 1080 },
  { name: '晚间', range: '18:00–23:00', test: (m) => m >= 1080 && m < 1380 },
].map((b) => {
  const ps = personas.filter((p) => b.test(p.slot))
  return { ...b, ps, done: ps.filter((p) => p.outcome === 'success').length, avg: ps.length ? ps.reduce((s, p) => s + avg(p.id), 0) / ps.length : null }
})
const scatter = personas.map((p) => ({ p, x: p.slot, y: avg(p.id), n: steps[p.id].length }))

// —— J / K 在问题之间切换 ——
const active = ref(-1)
function onKey(e) {
  if (drawers.stack.length || e.target.closest('input, textarea')) return
  const list = shownIssues.value
  if (e.key === 'j' || e.key === 'J') active.value = Math.min(list.length - 1, active.value + 1)
  else if (e.key === 'k' || e.key === 'K') active.value = Math.max(0, active.value - 1)
  else if (e.key === 'Enter' && active.value >= 0) return openDrawer({ type: 'finding', id: list[active.value].id })
  else return
  document.getElementById(list[active.value].id)?.scrollIntoView({ block: 'center', behavior: 'smooth' })
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

const toc = [
  ['ov', '总览'], ['issues', '问题清单'], ['highlights', '亮点'], ['voices', '公开声音与沉默信号'],
  ['dynamics', '舆论动态'], ['timeofday', '分时段体验差异'], ['scout', '说明书与实际不一致'],
]
const scrollTo = (id) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
const sx = (m) => 36 + (m / 1440) * 424
const sy = (v) => 20 + ((1 - v) / 2) * 160
</script>

<template>
  <div class="page report">
    <header class="page-head">
      <div>
        <div class="eyebrow">报告 · {{ run.id }}</div>
        <h1 class="page-title">青檀表单 v2.4 · 模拟体验报告</h1>
        <p class="page-sub">10 名模拟人物在 D1 00:00–24:00 的模拟时间线上真实使用了产品，并在社区中讨论。每条结论都附证据，三次点击内可到达截图、轨迹和录像。</p>
        <div class="row meta">
          <span class="realtime">{{ run.startedAt }} → {{ run.endedAt.slice(11) }}</span>
          <span class="faint">·</span><span class="faint">{{ run.model }}</span>
          <span class="faint">·</span><span class="faint">{{ run.browser }}</span>
        </div>
      </div>
      <div class="row">
        <button class="btn btn-secondary" type="button" @click="toast('演示数据：真实版本导出 PDF / Markdown')"><Download />导出报告</button>
        <button class="btn btn-primary" type="button" @click="router.push({ name: 'review', params: { runId: 'run-20261003-c' } })">
          <RotateCcw />复测 v2.5-rc <span class="cost">≈ ¥{{ run.estimate.min }}–{{ run.estimate.max }} · {{ run.estimate.minutes }} 分钟</span>
        </button>
      </div>
    </header>

    <div class="layout">
      <div class="content">
        <!-- 01 总览 -->
        <section id="ov" class="section first">
          <div class="section-head"><span class="n">01</span><h2>总览</h2><span class="aside">来源：体验记录 · 离场问卷 · 10 名人物</span></div>
          <p class="conclusion">
            模拟中 <b class="num">{{ taskedDone.length }}/{{ tasked.length }}</b> 名有任务的人物完成了任务。
            <b>2 个 S1 问题</b>分别阻断了注册和手机导出；另有 <b class="num">{{ withheld.length }}</b> 条体验没有在社区说出，其中「手机端找不到导出」只出现在私下记录中。
          </p>
          <div class="grid g4 kpis">
            <div class="panel tight kpi">
              <div class="k">任务完成</div>
              <div class="v big">{{ taskedDone.length }}<small>/{{ tasked.length }}</small></div>
              <DotMatrix :x="taskedDone.length" :y="tasked.length" :show-text="false" />
              <div class="d">另有 2 名自由探索人物完成探索</div>
            </div>
            <div class="panel tight kpi">
              <div class="k">推荐意愿 NPS</div>
              <div class="v big">{{ nps.score }}</div>
              <div class="d num">推荐 {{ nps.promoters }} · 被动 {{ nps.passives }} · 贬损 {{ nps.detractors }}（共 10）</div>
              <div class="d faint">样本仅 10 人，仅作方向参考</div>
            </div>
            <div class="panel tight kpi">
              <div class="k">问题</div>
              <div class="sevs">
                <span v-for="s in [1, 2, 3, 4]" :key="s" class="sv"><SevTag :sev="s" /><b class="num">{{ issueCount(s) }}</b></span>
              </div>
              <div class="d">亮点 {{ highlights.length }} 条</div>
            </div>
            <div class="panel tight kpi">
              <div class="k">未说出的体验</div>
              <div class="v big">{{ withheld.length }}<small> 条</small></div>
              <div class="d">发言者 {{ unsaidSpeakers }} 条 · 潜水者 {{ unsaidLurkers }} 条</div>
              <div class="d faint">实际花费 ¥{{ run.actual.cny }} · {{ run.actual.minutes }} 分钟</div>
            </div>
          </div>

          <div class="ovgrid">
          <div class="panel flush flows">
            <div class="table-wrap">
              <table class="data">
                <thead><tr><th>关键流程</th><th>负责人物</th><th>完成</th><th class="r">平均步数</th><th>结果</th></tr></thead>
                <tbody>
                  <tr v-for="f in flowsS" :key="f.id" @click="openDrawer({ type: 'persona', pid: f.people.find((p) => p.outcome === 'quit')?.id || f.people[0].id })">
                    <td><b>{{ f.name }}</b> <span class="faint num">{{ f.id }}</span></td>
                    <td><span class="row"><PersonaChip v-for="p in f.people" :key="p.id" :pid="p.id" /></span></td>
                    <td><DotMatrix :x="f.done.length" :y="f.people.length" /></td>
                    <td class="r num">{{ (f.people.reduce((s, p) => s + steps[p.id].length, 0) / f.people.length).toFixed(1) }}</td>
                    <td><span class="row"><StatusDot v-for="p in f.people" :key="p.id" :status="p.outcome === 'quit' ? 'quit' : 'done'" /></span></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <div class="panel tight"><NpsChart /></div>
          </div>
          <div class="note cov">
            <Info />
            <div>
              <b>覆盖说明</b>：服务端时间无法模拟，只模拟了浏览器时区（Asia/Shanghai）；
              模型不支持视频，回放分析改用截图序列；自由探索人物 2/10（建议约 3）；
              测试账号未覆盖付费用户。
            </div>
          </div>
        </section>

        <!-- 02 问题清单 -->
        <section id="issues" class="section">
          <div class="section-head">
            <span class="n">02</span><h2>问题清单</h2>
            <span class="aside">按「影响人数 × 严重度 × 证据强度」排序，不按点赞数 · <kbd>J</kbd> <kbd>K</kbd> 切换 <kbd>Enter</kbd> 打开</span>
          </div>
          <div class="seg filt" role="group" aria-label="按严重度筛选">
            <button type="button" :aria-pressed="sevFilter === 'all'" @click="sevFilter = 'all'">全部 {{ issues.length }}</button>
            <button type="button" :aria-pressed="sevFilter === '1'" @click="sevFilter = '1'">S1 致命 {{ issueCount(1) }}</button>
            <button type="button" :aria-pressed="sevFilter === '2'" @click="sevFilter = '2'">S2 严重 {{ issueCount(2) }}</button>
            <button type="button" :aria-pressed="sevFilter === '34'" @click="sevFilter = '34'">S3–S4 {{ issueCount(3) + issueCount(4) }}</button>
          </div>
          <div class="flist">
            <FindingCard v-for="(f, i) in shownIssues" :key="f.id" :f="f" :rank="i + 1" :active="active === i" />
          </div>
        </section>

        <!-- 03 亮点 -->
        <section id="highlights" class="section">
          <div class="section-head"><span class="n">03</span><h2>亮点</h2></div>
          <div class="grid g3">
            <FindingCard v-for="f in highlights" :key="f.id" :f="f" />
          </div>
        </section>

        <!-- 04 公开声音与沉默信号 -->
        <section id="voices" class="section">
          <div class="section-head"><span class="n">04</span><h2>公开声音与沉默信号</h2></div>
          <p class="lead">社区里说出的、体验了但没说的、私下问卷，是三种不同的信息。<b>{{ silentTopics.length }} 个问题只出现在沉默信号里</b>：{{ silentTopics.map((t) => t.key).join('、') }}。</p>

          <div class="grid g3 vcols">
            <div>
              <div class="vh"><span class="tag public">说出的</span><span class="faint num">{{ posts.length }} 帖 · {{ posts.reduce((s, p) => s + p.comments.length, 0) }} 评论</span></div>
              <div class="vstack">
                <VoiceCard v-for="p in posts" :key="p.id" kind="public" :pid="p.author" :t="p.t" action="发帖" :text="p.title" :evidence="p.evidence.slice(0, 1)" />
              </div>
            </div>
            <div>
              <div class="vh"><span class="tag withheld">未说出的</span><span class="faint num">{{ withheld.length }} 条</span></div>
              <div class="vstack">
                <VoiceCard v-for="(w, i) in withheld" :key="i" kind="withheld" :pid="w.pid" :t="w.t" :text="w.item" :reason="w.reason" :evidence="w.evidence.slice(0, 1)" />
              </div>
            </div>
            <div>
              <div class="vh"><span class="tag private">私下 · 问卷</span><span class="faint num">10/10 作答</span></div>
              <div class="vstack">
                <VoiceCard v-for="pid in ['p8', 'p3', 'p1', 'p6', 'p4']" :key="pid" kind="private" :pid="pid" :text="surveys[pid].unspoken.startsWith('没有') ? surveys[pid].worst : surveys[pid].unspoken" :extra="`NPS ${surveys[pid].nps}`" />
              </div>
            </div>
          </div>

          <h3 class="sub">公开结论与私下结论</h3>
          <div class="grid g2 compare">
            <div class="panel tight">
              <div class="vh"><span class="tag public">公开讨论的焦点</span><span class="faint">按提及次数</span></div>
              <div v-for="t in [...topics].sort((a, b) => b.public.length - a.public.length)" :key="t.key" class="trow">
                <span class="tk">{{ t.key }}</span>
                <span class="barw"><i class="pub" :style="{ width: t.public.length * 22 + '%' }"></i></span>
                <span class="num tn">{{ t.public.length }}</span>
              </div>
            </div>
            <div class="panel tight">
              <div class="vh"><span class="tag private">私下的体验问题</span><span class="faint">按涉及人数</span></div>
              <div v-for="t in [...topics].sort((a, b) => b.public.length - a.public.length)" :key="t.key" class="trow">
                <span class="tk">{{ t.key }}<span v-if="!t.public.length" class="tag withheld only">仅私下</span></span>
                <span class="barw"><i class="pri" :style="{ width: t.private.length * 22 + '%' }"></i></span>
                <span class="num tn">{{ t.private.length }}</span>
              </div>
            </div>
          </div>

          <h3 class="sub">说法不一致的人物 · {{ inconsistencies.length }}</h3>
          <div class="incons">
            <div v-for="x in inconsistencies" :key="x.pid" class="inc">
              <div class="who"><PersonaChip :pid="x.pid" /></div>
              <div class="voice public"><div class="who2 faint">公开</div>{{ x.public }}</div>
              <div class="voice private"><div class="who2 kind">私下</div>{{ x.private }}</div>
              <div class="evc"><EvTag v-for="(e, i) in x.evidence" :key="i" :ev="e" /></div>
            </div>
          </div>
        </section>

        <!-- 05 舆论动态 -->
        <section id="dynamics" class="section">
          <div class="section-head"><span class="n">05</span><h2>舆论动态</h2></div>
          <p class="lead">3 名人物在体验前看到了帖子并形成预期。其中 2 人的预期被体验印证，并且都在任务中放弃——讨论放大了已有的问题，但没有制造新问题。</p>
          <div class="panel"><InfluenceGraph /></div>
        </section>

        <!-- 06 分时段 -->
        <section id="timeofday" class="section">
          <div class="section-head"><span class="n">06</span><h2>分时段体验差异</h2></div>
          <p class="lead">晚间与深夜体验的手机人物平均满意度明显更低；同样在深夜，开发者孙立行（{{ fmt(P.p9.slot) }}）完成了任务，而疲惫的王思源（{{ fmt(P.p7.slot) }}）绕路才完成。</p>
          <div class="grid g2">
            <div class="panel">
              <div class="label">各人物体验时刻与平均满意度</div>
              <svg viewBox="0 0 480 214" width="100%" role="img" aria-label="散点图：横轴为体验开始的模拟时刻，纵轴为该人物全程平均满意度。">
                <rect :x="sx(0)" y="20" :width="sx(360) - sx(0)" height="160" fill="var(--surface-2)" />
                <rect :x="sx(1380)" y="20" :width="sx(1440) - sx(1380)" height="160" fill="var(--surface-2)" />
                <line :x1="sx(0)" :x2="sx(1440)" :y1="sy(0)" :y2="sy(0)" stroke="var(--border-strong)" stroke-dasharray="3 3" />
                <text x="0" :y="sy(1) + 4" class="ax">满意</text><text x="0" :y="sy(0) + 4" class="ax">0</text><text x="0" :y="sy(-1) + 4" class="ax">受挫</text>
                <text v-for="h in [0, 6, 12, 18, 24]" :key="h" :x="sx(h * 60)" y="202" class="ax mid">{{ String(h).padStart(2, '0') }}:00</text>
                <g v-for="d in scatter" :key="d.p.id" class="sp" tabindex="0" role="button" :aria-label="`${d.p.realname}：${fmt(d.x)} 体验，平均满意度 ${d.y.toFixed(2)}`"
                   @click="openDrawer({ type: 'persona', pid: d.p.id })" @keydown.enter="openDrawer({ type: 'persona', pid: d.p.id })">
                  <circle :cx="sx(d.x)" :cy="sy(d.y)" :r="4 + d.n / 3" :fill="d.p.color" opacity=".85" stroke="var(--surface)" stroke-width="1.5" />
                  <text :x="sx(d.x)" :y="sy(d.y) - 9 - d.n / 3" class="lb">{{ d.p.realname }}</text>
                </g>
              </svg>
              <div class="source">来源：体验记录 · 10 名人物 · 点的大小为步数 · 阴影为夜间</div>
            </div>
            <div class="panel flush">
              <table class="data">
                <thead><tr><th>时段</th><th>人物</th><th>完成</th><th class="r">平均满意度</th></tr></thead>
                <tbody>
                  <tr v-for="b in bands" :key="b.name" @click="b.ps[0] && openDrawer({ type: 'persona', pid: b.ps[0].id })">
                    <td><b>{{ b.name }}</b> <span class="num faint">{{ b.range }}</span></td>
                    <td><span class="row"><PersonaChip v-for="p in b.ps" :key="p.id" :pid="p.id" /></span></td>
                    <td><DotMatrix :x="b.done" :y="b.ps.length" /></td>
                    <td class="r num" :style="{ color: b.avg < 0 ? 'var(--neg)' : 'var(--text)' }">{{ b.avg == null ? '—' : (b.avg > 0 ? '+' : '') + b.avg.toFixed(2) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <div class="grid g2 pair">
            <div class="panel tight"><EmotionCurve :pids="['p2']" :title="`白天的开发者 · 周远 · ${fmt(P.p2.slot)}`" :height="130" /></div>
            <div class="panel tight"><EmotionCurve :pids="['p3']" :title="`午休的小白手机用户 · 陈默 · ${fmt(P.p3.slot)}`" :height="130" /></div>
          </div>
        </section>

        <!-- 07 侦察 -->
        <section id="scout" class="section">
          <div class="section-head"><span class="n">07</span><h2>说明书与实际不一致</h2><span class="aside">来源：侦察 · 1 个浏览会话</span></div>
          <div class="panel flush">
            <div class="table-wrap">
              <table class="data">
                <thead><tr><th>位置</th><th>使用说明写的</th><th>侦察看到的</th><th>关联发现</th></tr></thead>
                <tbody>
                  <tr v-for="s in scout" :key="s.id" @click="s.linked && openDrawer({ type: 'finding', id: s.linked })">
                    <td><b>{{ s.area }}</b></td><td class="wrap muted">{{ s.manual }}</td><td class="wrap">{{ s.actual }}</td>
                    <td><span v-if="s.linked" class="row"><SevTag :sev="findingById[s.linked].sev" /><span class="num faint">{{ s.linked }}</span></span><span v-else class="faint">—</span></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </section>
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
.meta { margin-top: var(--sp-3); font-size: var(--fs-xs); }
.layout { display: grid; grid-template-columns: minmax(0, 1fr) 180px; gap: var(--sp-6); }
.content { min-width: 0; }
.section.first { margin-top: 0; }
.toc { position: sticky; top: 84px; align-self: start; display: flex; flex-direction: column; gap: 2px; font-size: var(--fs-sm); }
.toc .label { margin-bottom: var(--sp-2); }
.toc a { color: var(--text-2); padding: 4px 0; display: flex; gap: var(--sp-2); text-decoration: none; }
.toc a:hover { color: var(--text); }
.toc .num { color: var(--text-3); font-size: var(--fs-xs); padding-top: 2px; }
.conclusion { font-size: var(--fs-lg); line-height: 1.7; margin: 0 0 var(--sp-5); max-width: 860px; }
.kpis { margin-bottom: var(--sp-4); }
.sevs { display: grid; grid-template-columns: 1fr 1fr; gap: 6px var(--sp-3); margin: var(--sp-2) 0; }
.sv { display: flex; align-items: center; justify-content: space-between; gap: var(--sp-2); }
.sv b { font-size: var(--fs-lg); }
.ovgrid { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr); gap: var(--sp-4); margin-bottom: var(--sp-3); align-items: start; }
@media (max-width: 1279px) { .ovgrid { grid-template-columns: 1fr; } }
.cov { font-size: var(--fs-xs); }
.flows .row { flex-wrap: nowrap; }
.filt { margin-bottom: var(--sp-4); }
.flist { display: grid; gap: var(--sp-3); }
.vcols { align-items: start; }
.vh { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--sp-3); font-size: var(--fs-xs); }
.vstack { display: grid; gap: var(--sp-2); }
.sub { font-size: var(--fs-lg); margin: var(--sp-6) 0 var(--sp-3); }
.trow { display: grid; grid-template-columns: 170px 1fr 24px; gap: var(--sp-3); align-items: center; height: 32px; font-size: var(--fs-sm); }
.tk { display: flex; align-items: center; gap: 6px; white-space: nowrap; }
.only { height: 18px; font-size: 11px; }
.barw { height: 8px; background: var(--surface-2); border-radius: 4px; overflow: hidden; }
.barw i { display: block; height: 100%; border-radius: 4px; }
.barw .pub { background: var(--vis-public); }
.barw .pri { background: var(--vis-private); }
.tn { text-align: right; color: var(--text-2); }
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
  .trow { grid-template-columns: 130px 1fr 20px; }
}
</style>
