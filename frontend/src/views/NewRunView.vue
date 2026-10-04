<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { product, flows, capability } from '../mock/data.js'
import { Upload, Check, X, AlertTriangle, FileText, Cpu, Users, Loader } from 'lucide-vue-next'

const router = useRouter()
const step = ref(1)
const manual = ref(null) // 'ok' | 'bad'
const dragging = ref(false)
const fileName = computed(() => (manual.value === 'bad' ? 'qingtan_manual_draft.md' : 'qingtan_manual_v2.5.md'))

const required = computed(() => [
  { k: 'name / url', ok: true, v: `${product.name} · ${product.url}` },
  { k: 'allowed_domains', ok: true, v: product.allowedDomains.join('、') },
  { k: 'test_accounts', ok: manual.value === 'ok', v: manual.value === 'ok' ? product.accounts.map((a) => a.role).join('、') : '缺失：至少提供 1 个测试账号角色' },
  { k: 'forbidden_actions', ok: true, v: `${product.forbidden.length} 条` },
  { k: '# 关键流程', ok: true, v: `${flows.length} 条：${flows.map((f) => f.short).join('、')}` },
  { k: '# 已知问题', ok: manual.value === 'ok', v: manual.value === 'ok' ? '2 条（作为校准集）' : '缺失：没有已知问题时请写「暂无」' },
  { k: '# 目标用户', ok: true, v: product.targetUsers },
])
const missing = computed(() => required.value.filter((r) => !r.ok))

// 能力探测
const probeState = ref('idle') // idle | running | done
const shown = ref(0)
async function runProbe() {
  probeState.value = 'running'
  shown.value = 0
  for (let i = 0; i < capability.length; i++) { await new Promise((r) => setTimeout(r, 380)); shown.value = i + 1 }
  probeState.value = 'done'
}
const resultIcon = { pass: Check, degraded: AlertTriangle, fail: X }
const resultText = { pass: '通过', degraded: '降级', fail: '不支持' }

// 生成人物
const gen = ref(0)
const genLabels = ['解析说明书 → 产品模型', '侦察：用 1 个浏览会话核对网站', '维度矩阵：覆盖设备、技术、耐心、参与方式', '补全 10 名人物的身份、背景、性格与作息', '生成运行配置并校验分布约束']
async function generate() {
  for (let i = 1; i <= genLabels.length; i++) { gen.value = i; await new Promise((r) => setTimeout(r, 520)) }
  router.push({ name: 'review', params: { runId: 'run-20261003-c' } })
}
function onDrop(e) { dragging.value = false; manual.value = 'ok'; e.preventDefault() }
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <div class="eyebrow">新建运行</div>
        <h1 class="page-title">新建运行</h1>
        <p class="page-sub">上传规定格式的使用说明。主 Agent 会先校验必填项，再探测模型能力、侦察网站并生成人物。到运行前审核之前，只会产生少量模型费用。</p>
      </div>
    </header>

    <ol class="stepper">
      <li v-for="(s, i) in [['使用说明', FileText], ['能力探测', Cpu], ['生成人物', Users]]" :key="i" :class="{ on: step === i + 1, done: step > i + 1 }">
        <span class="sn num">{{ step > i + 1 ? '✓' : i + 1 }}</span><component :is="s[1]" class="si" /><span>{{ s[0] }}</span>
      </li>
    </ol>

    <!-- 1 -->
    <section v-if="step === 1" class="grid g2 s1">
      <div>
        <label class="drop" :class="{ dragging }" @dragover.prevent="dragging = true" @dragleave="dragging = false" @drop="onDrop">
          <Upload />
          <b>拖入使用说明（.md）</b>
          <span class="faint">YAML front matter 放机器读取的字段，正文用固定标题 · 模板见 docs/product_manual_template.md</span>
          <input type="file" accept=".md" class="sr-only" @change="manual = 'ok'" />
        </label>
        <div class="row samples">
          <button class="btn btn-secondary sm" type="button" @click="manual = 'ok'">载入示例说明书</button>
          <button class="btn btn-ghost sm" type="button" @click="manual = 'bad'">载入有缺项的说明书</button>
        </div>
      </div>
      <div class="panel" v-if="manual">
        <div class="panel-head"><FileText class="hi" /><h3 class="num fn">{{ fileName }}</h3>
          <span class="aside" v-if="!missing.length"><span class="tag pos"><span class="dot"></span>校验通过</span></span>
          <span class="aside" v-else><span class="tag neg"><span class="dot"></span>缺少 {{ missing.length }} 项</span></span>
        </div>
        <ul class="req">
          <li v-for="r in required" :key="r.k" :class="{ bad: !r.ok }">
            <component :is="r.ok ? Check : X" class="ri" />
            <code>{{ r.k }}</code><span class="rv">{{ r.v }}</span>
          </li>
        </ul>
        <div v-if="missing.length" class="warn"><AlertTriangle /><div>说明书已退回：缺少 {{ missing.map((m) => m.k).join('、') }}。补全后重新上传，不会产生费用。</div></div>
        <div class="row end">
          <button class="btn btn-primary" type="button" :disabled="!!missing.length" @click="step = 2">下一步：能力探测</button>
        </div>
      </div>
      <div class="panel empty" v-else>
        <p class="faint">上传使用说明，开始第一次运行。校验结果会显示在这里。</p>
      </div>
    </section>

    <!-- 2 -->
    <section v-else-if="step === 2" class="panel s2">
      <div class="panel-head"><h3>模型能力探测</h3><span class="aside faint">测试样本都带随机答案，防止模型蒙对或假装看到内容</span></div>
      <table class="data">
        <thead><tr><th>探测项</th><th>结果</th><th>说明</th></tr></thead>
        <tbody>
          <tr v-for="(c, i) in capability" :key="c.item" :class="{ pend: i >= shown }">
            <td><b>{{ c.item }}</b></td>
            <td>
              <span v-if="i < shown" class="tag" :class="{ pos: c.result === 'pass', confused: c.result === 'degraded', neg: c.result === 'fail' }"><component :is="resultIcon[c.result]" />{{ resultText[c.result] }}</span>
              <span v-else-if="probeState === 'running' && i === shown" class="faint row"><Loader class="spin" />探测中</span>
              <span v-else class="faint">—</span>
            </td>
            <td class="wrap muted">{{ i < shown ? c.detail : '' }}</td>
          </tr>
        </tbody>
      </table>
      <div class="note" v-if="probeState === 'done'" style="margin-top: var(--sp-4)"><Check />识图与工具调用都通过，可以继续。视频不支持，回放分析会改用截图序列。</div>
      <div class="row end">
        <button class="btn btn-ghost" type="button" @click="step = 1">返回</button>
        <button v-if="probeState !== 'done'" class="btn btn-primary" type="button" :disabled="probeState === 'running'" @click="runProbe">开始探测 <span class="cost">≈ ¥0.02 · 30 秒</span></button>
        <button v-else class="btn btn-primary" type="button" @click="step = 3">下一步：生成人物</button>
      </div>
    </section>

    <!-- 3 -->
    <section v-else class="panel s3">
      <div class="panel-head"><h3>生成人物与运行配置</h3></div>
      <p class="muted">主 Agent 会先侦察网站，再用维度矩阵保证 10 名人物的覆盖面，最后补全细节。生成结果需要你在运行前审核中确认。</p>
      <ol class="gen">
        <li v-for="(g, i) in genLabels" :key="i" :class="{ done: gen > i + 1, cur: gen === i + 1 }">
          <span class="gi"><Check v-if="gen > i + 1" /><Loader v-else-if="gen === i + 1" class="spin" /><i v-else></i></span>{{ g }}
        </li>
      </ol>
      <div class="row end">
        <button class="btn btn-ghost" type="button" :disabled="gen > 0" @click="step = 2">返回</button>
        <button class="btn btn-primary" type="button" :disabled="gen > 0" @click="generate">生成人物 <span class="cost">≈ ¥0.35 · 2 分钟</span></button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.stepper { list-style: none; padding: 0; margin: 0 0 var(--sp-5); display: flex; gap: var(--sp-2); }
.stepper li { display: flex; align-items: center; gap: var(--sp-2); padding: var(--sp-2) var(--sp-4); border-radius: var(--r-full); border: 1px solid var(--border); color: var(--text-3); font-size: var(--fs-sm); font-weight: 600; background: var(--surface); }
.stepper li.on { color: var(--text); border-color: var(--text); }
.stepper li.done { color: var(--text-2); }
.sn { width: 20px; height: 20px; border-radius: 50%; background: var(--surface-2); display: grid; place-items: center; font-size: var(--fs-xs); }
.on .sn { background: var(--text); color: var(--bg); }
.si { width: 16px; height: 16px; stroke-width: 1.5; }
.s1 { align-items: start; }
.drop { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: var(--sp-2); text-align: center; border: 1.5px dashed var(--border-strong); border-radius: var(--r-lg); padding: var(--sp-7) var(--sp-5); background: var(--surface); cursor: pointer; transition: border-color var(--dur-fast) var(--ease), background var(--dur-fast) var(--ease); }
.drop:hover, .drop.dragging { border-color: var(--accent); background: var(--accent-soft); }
.drop svg { width: 24px; height: 24px; stroke-width: 1.5; color: var(--text-2); }
.drop .faint { font-size: var(--fs-xs); max-width: 360px; }
.samples { margin-top: var(--sp-3); }
.hi { width: 16px; height: 16px; stroke-width: 1.5; }
.fn { font-size: var(--fs-sm); }
.req { list-style: none; margin: 0 0 var(--sp-4); padding: 0; }
.req li { display: grid; grid-template-columns: 16px 150px 1fr; gap: var(--sp-3); align-items: start; padding: var(--sp-2) 0; border-bottom: 1px solid var(--border); font-size: var(--fs-sm); }
.ri { width: 16px; height: 16px; stroke-width: 1.5; color: var(--pos); margin-top: 3px; }
.req .bad .ri, .req li.bad .rv { color: var(--neg); }
.rv { color: var(--text-2); }
.end { justify-content: flex-end; margin-top: var(--sp-4); }
.empty { display: grid; place-items: center; min-height: 220px; }
.pend td { color: var(--text-3); }
.tag svg { width: 12px; height: 12px; }
.wrap { white-space: normal; }
.spin { width: 14px; height: 14px; animation: spin 1s linear infinite; stroke-width: 1.5; }
@keyframes spin { to { transform: rotate(360deg); } }
.note svg { color: var(--pos); }
.gen { list-style: none; padding: 0; margin: var(--sp-4) 0; display: grid; gap: var(--sp-2); }
.gen li { display: flex; align-items: center; gap: var(--sp-3); font-size: var(--fs-sm); color: var(--text-3); }
.gen li.cur { color: var(--text); font-weight: 600; }
.gen li.done { color: var(--text-2); }
.gi { width: 18px; height: 18px; display: grid; place-items: center; }
.gi svg { width: 16px; height: 16px; stroke-width: 1.5; }
.gen li.done .gi svg { color: var(--pos); }
.gi i { width: 8px; height: 8px; border-radius: 50%; border: 1.5px solid var(--border-strong); display: block; }
@media (max-width: 959px) { .stepper { flex-wrap: wrap; } .req li { grid-template-columns: 16px 1fr; } .rv { grid-column: 2; } }
</style>
