<script setup>
import { reactive, computed } from 'vue'
import { useRouter } from 'vue-router'
import { personas, flows, scout, run } from '../mock/data.js'
import { label, fmt, hhmm, assignmentLabel } from '../lib/sim.js'
import { askConfirm, toast, seek, play } from '../lib/store.js'
import { AlertTriangle, Check, Undo2, RefreshCw } from 'lucide-vue-next'
import PersonaChip from '../components/PersonaChip.vue'
import SimTimeline from '../components/SimTimeline.vue'
import PartTag from '../components/PartTag.vue'

const router = useRouter()
const FIELDS = ['device', 'tech', 'patience', 'participation', 'assignment', 'slot']
const pick = (p) => Object.fromEntries(FIELDS.map((k) => [k, p[k]]))
const original = Object.fromEntries(personas.map((p) => [p.id, pick(p)]))
const draft = reactive(Object.fromEntries(personas.map((p) => [p.id, pick(p)])))
const STEPS = { low: [15, 4], normal: [40, 6], high: [80, 10] }

const edited = (pid) => FIELDS.some((k) => draft[pid][k] !== original[pid][k])
const editedCount = computed(() => personas.filter((p) => edited(p.id)).length)
function restore(pid) { Object.assign(draft[pid], original[pid]) }
function regen(pid) { toast(`已请求主 Agent 重新生成 ${personas.find((p) => p.id === pid).realname}（演示）`) }
const slotStr = (pid) => hhmm(draft[pid].slot)
function setSlot(pid, v) { const [h, m] = v.split(':').map(Number); if (!Number.isNaN(h)) draft[pid].slot = h * 60 + (m || 0) }
const slots = computed(() => Object.fromEntries(personas.map((p) => [p.id, draft[p.id].slot])))

// 覆盖情况检查（docs/plan.md 4.4 的分布约束）
const D = computed(() => Object.values(draft))
const n = (fn) => D.value.filter(fn).length
const checks = computed(() => {
  const band = (a, b) => D.value.some((d) => (a < b ? d.slot >= a && d.slot < b : d.slot >= a || d.slot < b))
  const parts = ['poster', 'commenter', 'reactor', 'lurker'].map((k) => n((d) => d.participation === k))
  return [
    ...flows.map((f) => ({ k: `「${f.name}」由几个人负责`, v: n((d) => d.assignment === f.id), need: 2, text: (v) => `${v} 人` })),
    { k: '自由探索', v: n((d) => d.assignment === 'explore'), need: 3, text: (v) => `${v}/10（建议约 3）`, soft: true },
    { k: '开发者', v: n((d) => d.tech === 'developer'), need: 2, text: (v) => `${v} 人` },
    { k: '手机用户', v: n((d) => d.device === 'mobile'), need: 4, text: (v) => `${v} 人` },
    { k: '低耐心', v: n((d) => d.patience === 'low'), need: 3, text: (v) => `${v} 人` },
    { k: '参与方式（发帖 3 · 评论 3 · 点赞 2 · 潜水 2）', v: parts.join(' · '), ok: parts.join() === '3,3,2,2', text: (v) => v },
    { k: '明显的未说出倾向', v: personas.filter((p) => p.withhold === '高').length, need: 2, text: (v) => `${v} 人` },
    { k: '体验时段覆盖早、午、晚、深夜', v: [band(360, 660), band(660, 840), band(1080, 1380), band(1380, 360)].filter(Boolean).length, need: 4, text: (v) => `${v}/4 个时段` },
  ].map((c) => ({ ...c, pass: c.ok ?? c.v >= c.need }))
})
const failing = computed(() => checks.value.filter((c) => !c.pass))

// 费用预估：随人设约束变化
const calls = computed(() => Math.round(D.value.reduce((s, d) => s + STEPS[d.patience][0], 0) * 1.1 + 150))
const est = computed(() => ({ min: Math.round(calls.value * 0.0078), max: Math.round(calls.value * 0.014) }))

async function start() {
  const ok = await askConfirm({
    title: `开始运行？预计花费 ¥${est.value.min}–${est.value.max}，耗时 ${run.estimate.minutes} 分钟`,
    body: `将创建 10 个 Steel 云端浏览器会话，并按模拟时间线推进约 ${calls.value} 次模型调用。运行中可以随时暂停或终止，已产生的费用不会退回。${failing.value.length ? `仍有 ${failing.value.length} 项覆盖要求未满足。` : ''}`,
    confirmText: '确认并开始运行',
  })
  if (!ok) return
  toast('演示：用上一次运行的数据回放运行现场')
  seek(0)
  router.push({ name: 'live', params: { runId: 'run-20261003-b' }, query: { t: 'D1-00:00' } }).then(play)
}
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <div class="eyebrow">运行前审核 · run-20261003-c</div>
        <h1 class="page-title">青檀表单 v2.5-rc · 运行前审核</h1>
        <p class="page-sub">主 Agent 生成的人物、作息和配置都是草稿。确认之前不会产生浏览器和模型费用。修改过的人物会标出，可以一键恢复。</p>
      </div>
      <span class="status st-wait"><i></i>等待审核</span>
    </header>

    <!-- 1 人物列表 -->
    <section class="section first">
      <div class="section-head"><span class="n">1</span><h2>人物</h2><span class="aside">{{ editedCount ? `已修改 ${editedCount} 人` : '未修改' }} · 修改耐心会同步调整步数上限</span></div>
      <div class="panel flush">
        <div class="table-wrap">
          <table class="data edit">
            <thead><tr><th>人物</th><th>身份</th><th>设备</th><th>技术</th><th>耐心 · 步数</th><th>参与方式</th><th>任务</th><th>体验时刻</th><th></th></tr></thead>
            <tbody>
              <tr v-for="p in personas" :key="p.id" :class="{ changed: edited(p.id) }">
                <td><span class="row"><PersonaChip :pid="p.id" /><span v-if="edited(p.id)" class="tag edited">已修改</span></span></td>
                <td class="muted">{{ p.age }} · {{ p.profession }}</td>
                <td><select class="input sm" v-model="draft[p.id].device" :aria-label="`${p.realname} 设备`"><option value="mobile">手机</option><option value="desktop">桌面</option></select></td>
                <td><select class="input sm" v-model="draft[p.id].tech"><option value="novice">小白</option><option value="normal">普通</option><option value="developer">开发者</option></select></td>
                <td><span class="row nw"><select class="input sm" v-model="draft[p.id].patience"><option value="low">低</option><option value="normal">中</option><option value="high">高</option></select><span class="num faint">{{ STEPS[draft[p.id].patience][0] }} 步</span></span></td>
                <td><select class="input sm" v-model="draft[p.id].participation"><option v-for="(v, k) in label.participation" :key="k" :value="k">{{ v }}</option></select></td>
                <td><select class="input sm" v-model="draft[p.id].assignment"><option v-for="f in flows" :key="f.id" :value="f.id">{{ f.short }}</option><option value="explore">自由探索</option></select></td>
                <td><input class="input sm num slot" type="time" :value="slotStr(p.id)" @change="setSlot(p.id, $event.target.value)" :aria-label="`${p.realname} 体验时刻`" /></td>
                <td class="r">
                  <button v-if="edited(p.id)" class="btn btn-ghost sm" type="button" @click="restore(p.id)"><Undo2 />恢复</button>
                  <button v-else class="btn btn-ghost sm icon" type="button" :aria-label="`重新生成 ${p.realname}`" title="重新生成" @click="regen(p.id)"><RefreshCw /></button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <!-- 2 作息 -->
    <section class="section">
      <div class="section-head"><span class="n">2</span><h2>作息时间表</h2><span class="aside">模拟 1 天 · 时间片 60 分钟 · 浏览并发上限 {{ run.concurrency }}</span></div>
      <SimTimeline rows show-activity :scrub="false" :slots="slots" />
    </section>

    <div class="grid g2 two">
      <!-- 3 覆盖 -->
      <section class="section">
        <div class="section-head"><span class="n">3</span><h2>覆盖情况检查</h2><span class="aside">{{ checks.length - failing.length }}/{{ checks.length }} 项满足</span></div>
        <div class="panel flush">
          <ul class="checks">
            <li v-for="c in checks" :key="c.k" :class="{ bad: !c.pass }">
              <component :is="c.pass ? Check : AlertTriangle" class="ci" />
              <span class="ck">{{ c.k }}</span>
              <span class="cv num">{{ c.text(c.v) }}</span>
            </li>
          </ul>
        </div>
        <p class="faint small">未满足的要求只做提醒，不阻止运行。</p>
      </section>

      <!-- 4 侦察 -->
      <section class="section">
        <div class="section-head"><span class="n">4</span><h2>侦察时发现的问题</h2><span class="aside">{{ scout.length }} 处</span></div>
        <div class="scouts">
          <div v-for="s in scout" :key="s.id" class="warn">
            <AlertTriangle />
            <div><b>{{ s.area }}</b>：使用说明写的是「{{ s.manual }}」，侦察时看到的是「{{ s.actual }}」。已经记为一条发现。</div>
          </div>
        </div>
      </section>
    </div>

    <!-- 5 费用 -->
    <section class="section">
      <div class="section-head"><span class="n">5</span><h2>确认运行</h2></div>
      <div class="panel gate">
        <div class="gt">10 个人物 · 模拟 1 天 · {{ flows.length }} 条关键流程</div>
        <div v-if="failing.length" class="warn"><AlertTriangle /><div>{{ failing.length }} 项覆盖要求未满足：{{ failing.map((c) => c.k).join('；') }}。</div></div>
        <div class="bar">
          <div class="est">
            <div><span class="label">预估费用</span><b class="num">¥{{ est.min }}–{{ est.max }}</b></div>
            <div><span class="label">预估耗时</span><b class="num">{{ run.estimate.minutes }} 分钟</b></div>
            <div><span class="label">模型调用</span><b class="num">≈ {{ calls }}</b></div>
            <div><span class="label">云端浏览器</span><b class="num">10 会话</b></div>
          </div>
          <div class="row">
            <button class="btn btn-ghost" type="button" @click="router.push('/new')">返回修改说明书</button>
            <button class="btn btn-primary" type="button" @click="start">确认并开始运行 <span class="cost">≈ ¥{{ est.min }}–{{ est.max }} · {{ run.estimate.minutes }} 分钟</span></button>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.section.first { margin-top: 0; }
.edit td { height: 48px; }
.edit tbody tr { cursor: default; }
.edit tr.changed { background: color-mix(in srgb, var(--accent-soft) 45%, transparent); }
.nw { flex-wrap: nowrap; }
.slot { width: 96px; }
.two { align-items: start; }
.two .section { margin-top: var(--sp-7); }
.checks { list-style: none; margin: 0; padding: 0; }
.checks li { display: flex; align-items: center; gap: var(--sp-3); padding: 0 var(--sp-4); height: 40px; border-bottom: 1px solid var(--border); font-size: var(--fs-sm); }
.checks li:last-child { border-bottom: none; }
.ci { width: 16px; height: 16px; stroke-width: 1.5; color: var(--pos); flex: none; }
.bad { background: var(--confused-soft); }
.bad .ci { color: var(--confused); }
.ck { flex: 1; min-width: 0; }
.cv { color: var(--text-2); font-size: var(--fs-xs); }
.small { font-size: var(--fs-xs); margin-top: var(--sp-2); }
.scouts { display: grid; gap: var(--sp-2); }
.gate { border-color: var(--border-strong); }
.gt { font-weight: 700; font-size: var(--fs-lg); margin-bottom: var(--sp-3); }
.bar { display: flex; justify-content: space-between; align-items: center; gap: var(--sp-4); flex-wrap: wrap; border-top: 1px solid var(--border); margin-top: var(--sp-4); padding-top: var(--sp-4); }
.est { display: flex; gap: var(--sp-6); font-size: var(--fs-sm); flex-wrap: wrap; }
.est b { font-size: var(--fs-xl); display: block; line-height: 1.4; }
</style>
