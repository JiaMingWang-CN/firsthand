<script setup>
// 新建运行：资料（只填网址，或完整说明书）→ 选择能力文件 → 分析资料。
// 分析由后端以子进程执行 orchestrator.phase1 analyze：读首页、生成产品模型并推荐人数与天数；
// 人数与天数在审核页确认（可改）后才生成人物。校验与命令行完全一致。
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client.js'
import { askConfirm } from '../lib/store.js'
import { Upload, Check, AlertTriangle, FileText, Cpu, Sparkles, Loader, Circle, X, Info, Globe } from 'lucide-vue-next'

const router = useRouter()
const step = ref(1)
const mode = ref('url') // 'url' 只填网址 | 'manual' 完整说明书
const text = ref('')
const fileName = ref('')
const checking = ref(false)
const checked = ref(null) // 校验通过时的说明书摘要
const checkError = ref('')
const dragging = ref(false)

// —— 只填网址：表单拼出只有 front matter（和可选两节）的说明书，后端按同一套规则校验 ——
const form = ref({ url: '', domains: '', name: '', positioning: '', users: '' })
const domainsTouched = ref(false)
function hostOf(url) {
  try { return new URL(url.trim()).hostname } catch { return '' }
}
function onUrl() {
  if (!domainsTouched.value) form.value.domains = hostOf(form.value.url)
  onEdit()
}
const domainList = computed(() => form.value.domains.split(/[\s,，、]+/).map((d) => d.trim()).filter(Boolean))
const yaml = (value) => JSON.stringify(value) // JSON 字符串是合法的 YAML 双引号标量
const built = computed(() => {
  const f = form.value
  const lines = ['---', `url: ${yaml(f.url.trim())}`, 'allowed_domains:', ...domainList.value.map((d) => `  - ${yaml(d)}`)]
  if (f.name.trim()) lines.push(`name: ${yaml(f.name.trim())}`)
  lines.push('---', '')
  if (f.positioning.trim()) lines.push('# 产品定位', '', f.positioning.trim(), '')
  if (f.users.trim()) lines.push('# 目标用户', '', f.users.trim(), '')
  return lines.join('\n')
})
const manualText = computed(() => (mode.value === 'url' ? built.value : text.value))
const canCheck = computed(() => (mode.value === 'url' ? form.value.url.trim() && domainList.value.length : text.value.trim()))
function setMode(m) { mode.value = m; onEdit() }

async function loadFile(file) {
  if (!file) return
  fileName.value = file.name
  text.value = await file.text()
  await check()
}
function onDrop(e) { dragging.value = false; loadFile(e.dataTransfer?.files?.[0]) }
function onEdit() { checked.value = null; checkError.value = '' }

// 校验项与 orchestrator/manual.py 一致：只有 url 与 allowed_domains 必填，其余缺了会降低结果的参考性
const REQUIREMENTS = [
  { group: '必填', key: 'url', label: 'url', value: (c) => c.url },
  { group: '必填', key: 'allowed_domains', label: 'allowed_domains', value: (c) => c.allowed_domains.join('、') },
  { group: '可选', key: 'name', label: 'name', value: (c) => (c.defaults.includes('name') ? `未填，用域名 ${c.name}` : c.name) },
  { group: '可选', key: 'test_accounts', label: 'test_accounts', value: (c) => c.test_accounts.join('、') },
  { group: '可选', key: 'forbidden_actions', label: 'forbidden_actions', value: (c) => `${c.forbidden_actions.length} 条` },
  { group: '可选', key: '产品定位', label: '# 产品定位', value: () => '已填写' },
  { group: '可选', key: '目标用户', label: '# 目标用户', value: () => '已填写' },
  { group: '可选', key: '核心功能', label: '# 核心功能', value: () => '已填写' },
  { group: '可选', key: '关键流程', label: '# 关键流程', value: (c) => `${c.flows.length} 条：${c.flows.map((f) => f.name).join('、')}` },
  { group: '可选', key: '已知问题', label: '# 已知问题', value: (c) => (c.known_issues ? '有（作为校准集，不进入生成人物的提示词）' : '') },
]
const requirements = computed(() => REQUIREMENTS.map((r) => {
  const gap = checked.value?.material.gaps.find((g) => g.item === r.key)
  const missing = checked.value && (gap || (r.key === '已知问题' && !checked.value.known_issues))
  return {
    ...r,
    state: checked.value ? (missing ? 'gap' : 'ok') : checkError.value && checkError.value.includes(r.key) ? 'bad' : 'todo',
    shown: checked.value ? (gap ? `未提供 · ${gap.effect}` : missing ? '未提供' : r.value(checked.value)) : r.group === '必填' ? '必填' : '可不填',
  }
}))
const groups = computed(() => [...new Set(REQUIREMENTS.map((r) => r.group))].map((g) => [g, requirements.value.filter((r) => r.group === g)]))
const LEVEL = { complete: 'pos', partial: 'confused', limited: 'neg' }
const stats = computed(() => `${text.value.length.toLocaleString('zh-CN')} 字 · ${text.value ? text.value.split('\n').length : 0} 行`)
const PLACEHOLDER = ['---', 'url: https://…', 'allowed_domains: […]', '# 以下都可以不填', 'name: 产品名', 'test_accounts: […]', 'forbidden_actions: […]', '---', '',
  '# 产品定位', '# 目标用户', '# 核心功能', '# 关键流程', '', '格式见 docs/product_manual_template.md'].join('\n')

async function check() {
  checked.value = null
  checkError.value = ''
  if (!canCheck.value) return
  checking.value = true
  try {
    checked.value = await api.checkManual(manualText.value)
  } catch (e) {
    checkError.value = e.message
  } finally {
    checking.value = false
  }
}

// 能力文件：与当前模型配置匹配的才会列出；复用可省去探测的模型调用
const capabilities = ref({ status: 'idle', items: [], error: '' })
const capability = ref('') // '' = 重新探测
onMounted(async () => {
  capabilities.value.status = 'loading'
  try {
    capabilities.value.items = await api.capabilities()
    capability.value = capabilities.value.items[0]?.id ?? ''
    capabilities.value.status = 'ready'
  } catch (e) {
    capabilities.value = { status: 'error', items: [], error: e.message }
  }
})
const when = (iso) => new Date(iso).toLocaleString('zh-CN', { hour12: false })

const starting = ref(false)
const startError = ref('')
const plan = computed(() => [
  capability.value ? `复用能力文件 ${capability.value}` : '重新探测模型能力（识图、工具调用、结构化输出、采样参数等）',
  '读取产品首页（只访问 allowed_domains 内的地址）',
  '主 Agent 根据资料和首页生成产品模型',
  '主 Agent 推荐模拟人数和天数，并说明理由',
])
async function analyze() {
  const ok = await askConfirm({
    title: capability.value ? '分析资料' : '探测模型能力并分析资料',
    body: `将${capability.value ? '' : '先探测模型能力（需要几次模型调用），再'}读取首页、调用当前配置的模型生成产品模型和人数、天数推荐，会产生模型用量。推荐结果在下一页确认或修改后，才会生成人物。`,
    confirmText: capability.value ? '开始分析' : '开始探测并分析',
  })
  if (!ok) return
  starting.value = true
  startError.value = ''
  try {
    const job = await api.newDraft(manualText.value, capability.value)
    router.push({ name: 'review', params: { draftId: job.draft } })
  } catch (e) {
    startError.value = e.message
  } finally {
    starting.value = false
  }
}
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <div class="eyebrow">新建运行</div>
        <h1 class="page-title">新建运行</h1>
        <p class="page-sub">最少只需要产品网址和允许访问的域名。资料越完整，人物和结论越可信；资料很少时会明确提示参考性有限。人数和天数由主 Agent 推荐，生成人物前可以修改。</p>
      </div>
    </header>

    <ol class="stepper">
      <li v-for="(s, i) in [['资料', FileText], ['模型能力', Cpu], ['分析与推荐', Sparkles]]" :key="i" :class="{ on: step === i + 1, done: step > i + 1 }">
        <span class="sn num">{{ step > i + 1 ? '✓' : i + 1 }}</span><component :is="s[1]" class="si" /><span>{{ s[0] }}</span>
      </li>
    </ol>

    <!-- 1 资料 -->
    <section v-if="step === 1" class="s1">
      <div class="left">
        <div class="seg modes" role="group" aria-label="资料形式">
          <button type="button" :aria-pressed="mode === 'url'" @click="setMode('url')">只填网址</button>
          <button type="button" :aria-pressed="mode === 'manual'" @click="setMode('manual')">完整说明书</button>
        </div>

        <div v-if="mode === 'url'" class="panel urlform">
          <label class="field"><span>产品网址 <b class="req">必填</b></span>
            <input v-model="form.url" class="input" type="url" placeholder="https://staging.example.com" aria-label="产品网址" @input="onUrl" /></label>
          <label class="field"><span>允许访问的域名 <b class="req">必填</b><em class="faint">人物只能访问这些主机；多个用逗号或空格分开</em></span>
            <input v-model="form.domains" class="input" placeholder="staging.example.com, auth.example.com" aria-label="允许访问的域名" @input="domainsTouched = true; onEdit()" /></label>
          <label class="field"><span>产品名称 <em class="faint">可选，不填用域名</em></span>
            <input v-model="form.name" class="input" aria-label="产品名称" @input="onEdit" /></label>
          <label class="field"><span>一句话说明产品 <em class="faint">可选：给谁用、解决什么问题</em></span>
            <textarea v-model="form.positioning" class="input area" rows="2" aria-label="产品定位" @input="onEdit"></textarea></label>
          <label class="field"><span>目标用户 <em class="faint">可选：人群、设备、常用时段</em></span>
            <textarea v-model="form.users" class="input area" rows="2" aria-label="目标用户" @input="onEdit"></textarea></label>
          <div class="ed-foot">
            <span class="faint"><Globe class="gl" />没写的内容由 AI 读取首页后推断；测试账号、关键流程等需要完整说明书</span>
            <button class="btn btn-primary sm" type="button" :disabled="!canCheck || checking" @click="check"><Loader v-if="checking" class="spin" />检查</button>
          </div>
        </div>

        <div v-else class="editor" :class="{ dragging }" @dragover.prevent="dragging = true" @dragleave.self="dragging = false" @drop.prevent="onDrop">
          <div class="ed-head">
            <FileText class="hi" />
            <b>使用说明</b>
            <span v-if="fileName" class="chip num">{{ fileName }}</span>
            <span class="faint ed-hint">粘贴 Markdown，或把 .md 文件拖到这里</span>
            <label class="btn btn-secondary sm pick"><Upload />选择文件
              <input type="file" accept=".md,text/markdown" class="sr-only" aria-label="选择使用说明文件" @change="loadFile($event.target.files[0]); $event.target.value = ''" />
            </label>
          </div>
          <textarea v-model="text" class="ed-text" spellcheck="false" aria-label="使用说明内容" :placeholder="PLACEHOLDER" @input="onEdit(); fileName = ''"></textarea>
          <div class="ed-foot">
            <span class="faint num">{{ stats }}</span>
            <span class="faint">校验只解析格式，不调用模型、不产生费用</span>
            <button class="btn btn-primary sm" type="button" :disabled="!canCheck || checking" @click="check"><Loader v-if="checking" class="spin" />校验</button>
          </div>
          <div v-if="dragging" class="drop-mask"><Upload />松开以载入文件</div>
        </div>
      </div>

      <aside class="panel checklist">
        <div class="panel-head">
          <h3>校验结果</h3>
          <span class="aside">
            <span v-if="checked" class="tag pos"><span class="dot"></span>校验通过</span>
            <span v-else-if="checkError" class="tag neg"><span class="dot"></span>未通过</span>
            <span v-else-if="checking" class="faint">正在校验…</span>
            <span v-else class="faint">尚未校验</span>
          </span>
        </div>
        <div v-if="checkError" class="warn" role="alert"><AlertTriangle /><div>{{ checkError }}。修改后重新校验。</div></div>
        <div v-if="checked" class="material" :class="checked.material.level" role="status">
          <span class="tag" :class="LEVEL[checked.material.level]"><span class="dot"></span>{{ { complete: '资料完整', partial: '资料不全', limited: '参考性有限' }[checked.material.level] }}</span>
          <span>{{ checked.material.summary }}</span>
        </div>
        <div v-for="[g, items] in groups" :key="g" class="req-group">
          <div class="req-title faint">{{ g }}</div>
          <ul class="req">
            <li v-for="r in items" :key="r.key" :class="r.state">
              <Check v-if="r.state === 'ok'" class="ri" /><X v-else-if="r.state === 'bad'" class="ri" /><Circle v-else class="ri" />
              <code>{{ r.label }}</code><span class="rv">{{ r.shown }}</span>
            </li>
          </ul>
        </div>
        <button v-if="checked" class="btn btn-primary next" type="button" @click="step = 2">下一步：模型能力</button>
      </aside>
    </section>

    <!-- 2 模型能力 -->
    <section v-else-if="step === 2" class="panel">
      <div class="panel-head"><h3>模型能力</h3><span class="aside faint">能力文件决定能否识图、调用工具、输出结构化结果和使用人物各自的采样参数；必须与当前模型配置一致</span></div>
      <p v-if="capabilities.status === 'loading'" class="faint">正在读取已有的能力文件…</p>
      <div v-else-if="capabilities.status === 'ready' && !capabilities.items.length" class="note"><Info />没有与当前模型配置一致、可复用的能力文件。探测不在这一步执行：进入下一步点“探测模型能力并分析资料”时，会先探测、再分析。</div>
      <div v-else-if="capabilities.status === 'error'" class="warn" role="alert"><AlertTriangle /><div>{{ capabilities.error }}</div></div>
      <fieldset v-else class="caps">
        <legend class="sr-only">能力文件</legend>
        <label v-for="c in capabilities.items" :key="c.id" class="cap" :class="{ on: capability === c.id }">
          <input v-model="capability" type="radio" name="cap" :value="c.id" />
          <span><b class="num">{{ c.id }}</b><span class="faint">探测于 {{ when(c.created_at) }}，与当前模型配置一致，可直接复用</span>
            <span v-if="!c.sampling" class="faint warn-text">没有通过采样参数检查（或探测时还没有这一项）：人物各自的温度、top_p 不会生效</span></span>
        </label>
        <label class="cap" :class="{ on: capability === '' }">
          <input v-model="capability" type="radio" name="cap" value="" />
          <span><b>重新探测</b><span class="faint">用随机答案的样本测试识图、工具调用、结构化输出和采样参数，会多花几次模型调用</span></span>
        </label>
      </fieldset>
      <div class="row end">
        <button class="btn btn-ghost" type="button" @click="step = 1">返回</button>
        <button class="btn btn-primary" type="button" :disabled="capabilities.status === 'loading'" @click="step = 3">下一步：分析资料</button>
      </div>
    </section>

    <!-- 3 分析与推荐 -->
    <section v-else class="panel">
      <div class="panel-head"><h3>分析资料并推荐人数与天数</h3><span class="aside faint">{{ checked?.name }}</span></div>
      <ol class="gen">
        <li v-for="(g, i) in plan" :key="i"><span class="gi"><i></i></span>{{ g }}</li>
      </ol>
      <p class="faint small">这一步不生成人物。下一页显示推荐的人数和天数（一般 30–50 人、50 天左右），确认或修改后再生成。</p>
      <div v-if="startError" class="warn" role="alert"><AlertTriangle /><div>{{ startError }}</div></div>
      <div class="row end">
        <button class="btn btn-ghost" type="button" :disabled="starting" @click="step = 2">返回</button>
        <button class="btn btn-primary" type="button" :disabled="starting" @click="analyze"><Loader v-if="starting" class="spin" />{{ capability ? '分析资料' : '探测模型能力并分析资料' }}</button>
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
.s1 { display: grid; grid-template-columns: minmax(0, 3fr) minmax(300px, 2fr); gap: var(--sp-4); align-items: start; }
.left { display: grid; gap: var(--sp-3); min-width: 0; }
.modes { justify-self: start; }
.urlform { display: grid; gap: var(--sp-3); }
.field { display: grid; gap: 6px; font-size: var(--fs-sm); font-weight: 600; }
.field em { font-style: normal; font-weight: 400; font-size: var(--fs-xs); margin-left: var(--sp-2); }
.field .req { font-size: var(--fs-xs); color: var(--neg); font-weight: 600; margin-left: 4px; }
.area { height: auto; padding: 8px 11px; resize: vertical; line-height: 1.6; font-weight: 400; }
.urlform .ed-foot { padding: 0; }
.gl { width: 14px; height: 14px; stroke-width: 1.5; vertical-align: -2px; margin-right: 4px; }
.material { display: grid; gap: 6px; padding: var(--sp-3); border-radius: var(--r-md); background: var(--surface-2); font-size: var(--fs-sm); }
.material .tag { justify-self: start; }
.warn-text { color: var(--confused); }
.editor { position: relative; display: flex; flex-direction: column; background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg); overflow: hidden; transition: border-color var(--dur-fast) var(--ease); }
.editor:focus-within { border-color: var(--border-strong); }
.editor.dragging { border-color: var(--accent); }
.ed-head, .ed-foot { display: flex; align-items: center; gap: var(--sp-3); padding: var(--sp-2) var(--sp-3) var(--sp-2) var(--sp-4); font-size: var(--fs-sm); }
.ed-head { border-bottom: 1px solid var(--border); min-height: 48px; }
.ed-foot { border-top: 1px solid var(--border); font-size: var(--fs-xs); }
.ed-foot .btn { margin-left: auto; }
.ed-hint { font-size: var(--fs-xs); margin-left: auto; }
.chip { font-size: var(--fs-xs); padding: 2px 8px; border-radius: var(--r-full); background: var(--surface-2); color: var(--text-2); max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pick { cursor: pointer; }
.pick svg { width: 14px; height: 14px; stroke-width: 1.5; }
.ed-text { border: none; outline: none; resize: vertical; min-height: 460px; padding: var(--sp-4); background: transparent; color: var(--text); font-family: var(--font-mono); font-size: var(--fs-xs); line-height: 1.7; tab-size: 2; }
.ed-text::placeholder { color: var(--text-3); }
.drop-mask { position: absolute; inset: 0; display: grid; place-content: center; justify-items: center; gap: var(--sp-2); background: color-mix(in srgb, var(--accent-soft) 92%, transparent); color: var(--text); font-weight: 600; pointer-events: none; }
.drop-mask svg { width: 28px; height: 28px; stroke-width: 1.5; }
.checklist { position: sticky; top: var(--sp-4); display: grid; gap: var(--sp-3); }
.checklist .panel-head { margin-bottom: 0; }
.req-title { font-size: var(--fs-xs); letter-spacing: .04em; margin-bottom: 2px; }
.hi { width: 16px; height: 16px; stroke-width: 1.5; }
.req { list-style: none; margin: 0; padding: 0; }
.req li { display: grid; grid-template-columns: 16px 140px 1fr; gap: var(--sp-3); align-items: start; padding: 6px 0; border-bottom: 1px solid var(--border); font-size: var(--fs-sm); }
.req li:last-child { border-bottom: none; }
.ri { width: 16px; height: 16px; stroke-width: 1.5; margin-top: 2px; color: var(--text-3); }
.req li.ok .ri { color: var(--pos); }
.req li.bad .ri, .req li.bad code { color: var(--neg); }
.req li.todo .rv, .req li.gap .rv { color: var(--text-3); }
.req li.gap .ri { color: var(--confused); }
.rv { color: var(--text-2); word-break: break-word; }
.next { justify-self: end; }
.note { display: flex; gap: var(--sp-2); align-items: flex-start; padding: var(--sp-3) var(--sp-4); margin-bottom: var(--sp-3); border-radius: var(--r-md); background: var(--surface-2); color: var(--text-2); font-size: var(--fs-sm); }
.note svg { width: 16px; height: 16px; stroke-width: 1.5; flex: none; margin-top: 2px; }
.end { justify-content: flex-end; margin-top: var(--sp-4); }
.caps { border: none; margin: 0; padding: 0; display: grid; gap: var(--sp-2); }
.cap { display: flex; gap: var(--sp-3); align-items: flex-start; padding: var(--sp-3) var(--sp-4); border: 1px solid var(--border); border-radius: var(--r-md); cursor: pointer; }
.cap.on { border-color: var(--text); }
.cap > span { display: grid; gap: 2px; font-size: var(--fs-sm); }
.cap .faint { font-size: var(--fs-xs); }
.gen { list-style: none; padding: 0; margin: var(--sp-2) 0 var(--sp-4); display: grid; gap: var(--sp-2); }
.gen li { display: flex; align-items: center; gap: var(--sp-3); font-size: var(--fs-sm); color: var(--text-2); }
.gi { width: 18px; height: 18px; display: grid; place-items: center; }
.gi i { width: 8px; height: 8px; border-radius: 50%; border: 1.5px solid var(--border-strong); display: block; }
.spin { width: 14px; height: 14px; animation: spin 1s linear infinite; stroke-width: 1.5; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 959px) { .stepper { flex-wrap: wrap; } .s1 { grid-template-columns: 1fr; } .checklist { position: static; } .ed-hint { display: none; } .ed-text { min-height: 320px; } .req li { grid-template-columns: 16px 1fr; } .rv { grid-column: 2; } }
</style>
