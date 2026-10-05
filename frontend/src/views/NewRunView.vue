<script setup>
// 新建运行：校验使用说明 → 选择能力文件（复用或重新探测）→ 生成人物草稿。
// 校验与命令行 orchestrator.phase1 完全一致；生成由后端以子进程执行同一条命令，完成后进入运行前审核。
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client.js'
import { askConfirm } from '../lib/store.js'
import { Upload, Check, AlertTriangle, FileText, Cpu, Users, Loader, Circle, X, Info } from 'lucide-vue-next'

const router = useRouter()
const step = ref(1)
const text = ref('')
const fileName = ref('')
const checking = ref(false)
const checked = ref(null) // 校验通过时的说明书摘要
const checkError = ref('')
const dragging = ref(false)

async function loadFile(file) {
  if (!file) return
  fileName.value = file.name
  text.value = await file.text()
  await check()
}
function onDrop(e) { dragging.value = false; loadFile(e.dataTransfer?.files?.[0]) }
function onEdit() { checked.value = null; checkError.value = ''; fileName.value = '' }

// 校验项与 orchestrator/manual.py 一致；未校验时列出要求，失败时标出报错里点名的项，通过时显示读到的值
const REQUIREMENTS = [
  { group: 'front matter', key: 'name', label: 'name / url', value: (c) => `${c.name} · ${c.url}` },
  { group: 'front matter', key: 'allowed_domains', label: 'allowed_domains', value: (c) => c.allowed_domains.join('、') },
  { group: 'front matter', key: 'test_accounts', label: 'test_accounts', value: (c) => c.test_accounts.join('、') },
  { group: 'front matter', key: 'forbidden_actions', label: 'forbidden_actions', value: (c) => `${c.forbidden_actions} 条` },
  { group: '正文章节', key: '产品定位', label: '# 产品定位', value: () => '已填写' },
  { group: '正文章节', key: '目标用户', label: '# 目标用户', value: () => '已填写' },
  { group: '正文章节', key: '核心功能', label: '# 核心功能', value: () => '已填写' },
  { group: '正文章节', key: '关键流程', label: '# 关键流程', value: (c) => `${c.flows.length} 条：${c.flows.map((f) => f.name).join('、')}` },
  { group: '可选', key: '已知问题', label: '# 已知问题', optional: true, value: (c) => (c.known_issues ? '有（作为校准集，不进入生成人物的提示词）' : '未提供') },
]
const requirements = computed(() => REQUIREMENTS.map((r) => ({
  ...r,
  state: checked.value ? 'ok' : checkError.value && checkError.value.includes(r.key) ? 'bad' : 'todo',
  shown: checked.value ? r.value(checked.value) : r.optional ? '可不填' : '必填',
})))
const groups = computed(() => [...new Set(REQUIREMENTS.map((r) => r.group))].map((g) => [g, requirements.value.filter((r) => r.group === g)]))
const stats = computed(() => `${text.value.length.toLocaleString('zh-CN')} 字 · ${text.value ? text.value.split('\n').length : 0} 行`)
const PLACEHOLDER = ['---', 'name: 产品名', 'url: https://…', 'allowed_domains: […]', 'test_accounts: […]', 'forbidden_actions: […]', '---', '',
  '# 产品定位', '# 目标用户', '# 核心功能', '# 关键流程', '', '格式见 docs/product_manual_template.md'].join('\n')

async function check() {
  checked.value = null
  checkError.value = ''
  if (!text.value.trim()) return
  checking.value = true
  try {
    checked.value = await api.checkManual(text.value)
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
  capability.value ? `复用能力文件 ${capability.value}` : '重新探测模型能力（识图、工具调用、结构化输出等）',
  '主 Agent 解析说明书，生成产品模型',
  '规划 10 人的维度分布，再并行补全每个人的身份、背景、性格与作息',
  '生成运行配置并校验分布约束',
])
async function generate() {
  const ok = await askConfirm({
    title: capability.value ? '生成人物草稿' : '探测模型能力并生成人物草稿',
    body: `将${capability.value ? '' : '先探测模型能力（识图、工具调用、结构化输出，需要几次模型调用），再'}调用当前配置的模型生成 10 名人物与运行配置，会产生模型用量。生成的草稿需要你在运行前审核中确认后，才会开始浏览与讨论。`,
    confirmText: capability.value ? '开始生成' : '开始探测并生成',
  })
  if (!ok) return
  starting.value = true
  startError.value = ''
  try {
    const job = await api.newDraft(text.value, capability.value)
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
        <p class="page-sub">上传规定格式的使用说明。先校验必填项（不调用模型），再选择能力文件并生成人物草稿；草稿要在运行前审核里确认后才会开始真实浏览。</p>
      </div>
    </header>

    <ol class="stepper">
      <li v-for="(s, i) in [['使用说明', FileText], ['模型能力', Cpu], ['生成人物', Users]]" :key="i" :class="{ on: step === i + 1, done: step > i + 1 }">
        <span class="sn num">{{ step > i + 1 ? '✓' : i + 1 }}</span><component :is="s[1]" class="si" /><span>{{ s[0] }}</span>
      </li>
    </ol>

    <!-- 1 使用说明 -->
    <section v-if="step === 1" class="s1">
      <div class="editor" :class="{ dragging }" @dragover.prevent="dragging = true" @dragleave.self="dragging = false" @drop.prevent="onDrop">
        <div class="ed-head">
          <FileText class="hi" />
          <b>使用说明</b>
          <span v-if="fileName" class="chip num">{{ fileName }}</span>
          <span class="faint ed-hint">粘贴 Markdown，或把 .md 文件拖到这里</span>
          <label class="btn btn-secondary sm pick"><Upload />选择文件
            <input type="file" accept=".md,text/markdown" class="sr-only" aria-label="选择使用说明文件" @change="loadFile($event.target.files[0]); $event.target.value = ''" />
          </label>
        </div>
        <textarea v-model="text" class="ed-text" spellcheck="false" aria-label="使用说明内容" :placeholder="PLACEHOLDER" @input="onEdit"></textarea>
        <div class="ed-foot">
          <span class="faint num">{{ stats }}</span>
          <span class="faint">校验只解析格式，不调用模型、不产生费用</span>
          <button class="btn btn-primary sm" type="button" :disabled="!text.trim() || checking" @click="check"><Loader v-if="checking" class="spin" />校验</button>
        </div>
        <div v-if="dragging" class="drop-mask"><Upload />松开以载入文件</div>
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
      <div class="panel-head"><h3>模型能力</h3><span class="aside faint">能力文件决定能否识图、调用工具和输出结构化结果；必须与当前模型配置一致</span></div>
      <p v-if="capabilities.status === 'loading'" class="faint">正在读取已有的能力文件…</p>
      <div v-else-if="capabilities.status === 'ready' && !capabilities.items.length" class="note"><Info />没有与当前模型配置一致、可复用的能力文件。探测不在这一步执行：进入下一步点“探测模型能力并生成人物”时，会先探测、再生成。</div>
      <div v-else-if="capabilities.status === 'error'" class="warn" role="alert"><AlertTriangle /><div>{{ capabilities.error }}</div></div>
      <fieldset v-else class="caps">
        <legend class="sr-only">能力文件</legend>
        <label v-for="c in capabilities.items" :key="c.id" class="cap" :class="{ on: capability === c.id }">
          <input v-model="capability" type="radio" name="cap" :value="c.id" />
          <span><b class="num">{{ c.id }}</b><span class="faint">探测于 {{ when(c.created_at) }}，与当前模型配置一致，可直接复用</span></span>
        </label>
        <label class="cap" :class="{ on: capability === '' }">
          <input v-model="capability" type="radio" name="cap" value="" />
          <span><b>重新探测</b><span class="faint">用随机答案的样本测试识图、工具调用与结构化输出，会多花几次模型调用</span></span>
        </label>
      </fieldset>
      <div class="row end">
        <button class="btn btn-ghost" type="button" @click="step = 1">返回</button>
        <button class="btn btn-primary" type="button" :disabled="capabilities.status === 'loading'" @click="step = 3">下一步：生成人物</button>
      </div>
    </section>

    <!-- 3 生成人物 -->
    <section v-else class="panel">
      <div class="panel-head"><h3>生成人物与运行配置</h3><span class="aside faint">{{ checked?.name }}</span></div>
      <ol class="gen">
        <li v-for="(g, i) in plan" :key="i"><span class="gi"><i></i></span>{{ g }}</li>
      </ol>
      <div v-if="startError" class="warn" role="alert"><AlertTriangle /><div>{{ startError }}</div></div>
      <div class="row end">
        <button class="btn btn-ghost" type="button" :disabled="starting" @click="step = 2">返回</button>
        <button class="btn btn-primary" type="button" :disabled="starting" @click="generate"><Loader v-if="starting" class="spin" />{{ capability ? '生成人物草稿' : '探测模型能力并生成人物' }}</button>
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
.req li.todo .rv { color: var(--text-3); }
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
