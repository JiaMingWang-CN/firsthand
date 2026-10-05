<script setup>
// 新建运行：校验使用说明 → 选择能力文件（复用或重新探测）→ 生成人物草稿。
// 校验与命令行 orchestrator.phase1 完全一致；生成由后端以子进程执行同一条命令，完成后进入运行前审核。
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client.js'
import { askConfirm } from '../lib/store.js'
import { Upload, Check, AlertTriangle, FileText, Cpu, Users, Loader } from 'lucide-vue-next'

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
    title: '生成人物草稿',
    body: `将调用当前配置的模型${capability.value ? '' : '（含能力探测）'}生成 10 名人物与运行配置，会产生模型用量。生成的草稿需要你在运行前审核中确认后，才会开始浏览与讨论。`,
    confirmText: '开始生成',
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
    <section v-if="step === 1" class="grid g2 s1">
      <div>
        <label class="drop" :class="{ dragging }" @dragover.prevent="dragging = true" @dragleave="dragging = false" @drop.prevent="onDrop">
          <Upload />
          <b>拖入或选择使用说明（.md）</b>
          <span class="faint">YAML front matter 放机器读取的字段，正文用固定标题 · 模板见 docs/product_manual_template.md</span>
          <input type="file" accept=".md,text/markdown" class="sr-only" aria-label="选择使用说明文件" @change="loadFile($event.target.files[0])" />
        </label>
        <label class="paste">
          <span class="faint">或直接粘贴内容</span>
          <textarea v-model="text" class="input" rows="8" spellcheck="false" aria-label="使用说明内容" @input="checked = null; checkError = ''"></textarea>
        </label>
        <div class="row end"><button class="btn btn-secondary" type="button" :disabled="!text.trim() || checking" @click="check">校验</button></div>
      </div>
      <div class="panel" v-if="checked">
        <div class="panel-head"><FileText class="hi" /><h3 class="fn">{{ fileName || checked.name }}</h3>
          <span class="aside"><span class="tag pos"><span class="dot"></span>校验通过</span></span>
        </div>
        <ul class="req">
          <li><Check class="ri" /><code>name / url</code><span class="rv">{{ checked.name }} · {{ checked.url }}</span></li>
          <li><Check class="ri" /><code>allowed_domains</code><span class="rv">{{ checked.allowed_domains.join('、') }}</span></li>
          <li><Check class="ri" /><code>test_accounts</code><span class="rv">{{ checked.test_accounts.join('、') }}</span></li>
          <li><Check class="ri" /><code>forbidden_actions</code><span class="rv">{{ checked.forbidden_actions }} 条</span></li>
          <li><Check class="ri" /><code># 关键流程</code><span class="rv">{{ checked.flows.length }} 条：{{ checked.flows.map((f) => f.name).join('、') }}</span></li>
          <li><Check class="ri" /><code># 已知问题</code><span class="rv">{{ checked.known_issues ? '有（作为校准集，不进入生成人物的提示词）' : '未提供' }}</span></li>
        </ul>
        <div class="row end"><button class="btn btn-primary" type="button" @click="step = 2">下一步：模型能力</button></div>
      </div>
      <div class="panel" v-else-if="checkError" role="alert">
        <div class="warn"><AlertTriangle /><div><b>说明书未通过校验</b>：{{ checkError }}。修改后重新校验，不会产生费用。</div></div>
      </div>
      <div class="panel empty" v-else>
        <p class="faint">{{ checking ? '正在校验…' : '上传或粘贴使用说明，校验结果会显示在这里。' }}</p>
      </div>
    </section>

    <!-- 2 模型能力 -->
    <section v-else-if="step === 2" class="panel">
      <div class="panel-head"><h3>模型能力</h3><span class="aside faint">能力文件决定能否识图、调用工具和输出结构化结果；必须与当前模型配置一致</span></div>
      <p v-if="capabilities.status === 'loading'" class="faint">正在读取已有的能力文件…</p>
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
        <button class="btn btn-primary" type="button" :disabled="starting" @click="generate"><Loader v-if="starting" class="spin" />生成人物草稿</button>
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
.drop { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: var(--sp-2); text-align: center; border: 1.5px dashed var(--border-strong); border-radius: var(--r-lg); padding: var(--sp-6) var(--sp-5); background: var(--surface); cursor: pointer; transition: border-color var(--dur-fast) var(--ease), background var(--dur-fast) var(--ease); }
.drop:hover, .drop.dragging { border-color: var(--accent); background: var(--accent-soft); }
.drop svg { width: 24px; height: 24px; stroke-width: 1.5; color: var(--text-2); }
.drop .faint { font-size: var(--fs-xs); max-width: 360px; }
.paste { display: grid; gap: var(--sp-1); margin-top: var(--sp-3); font-size: var(--fs-xs); }
.paste textarea { font-family: var(--font-mono); font-size: var(--fs-xs); resize: vertical; width: 100%; }
.hi { width: 16px; height: 16px; stroke-width: 1.5; }
.fn { font-size: var(--fs-sm); }
.req { list-style: none; margin: 0 0 var(--sp-4); padding: 0; }
.req li { display: grid; grid-template-columns: 16px 150px 1fr; gap: var(--sp-3); align-items: start; padding: var(--sp-2) 0; border-bottom: 1px solid var(--border); font-size: var(--fs-sm); }
.ri { width: 16px; height: 16px; stroke-width: 1.5; color: var(--pos); margin-top: 3px; }
.rv { color: var(--text-2); word-break: break-word; }
.end { justify-content: flex-end; margin-top: var(--sp-4); }
.empty { display: grid; place-items: center; min-height: 220px; }
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
@media (max-width: 959px) { .stepper { flex-wrap: wrap; } .req li { grid-template-columns: 16px 1fr; } .rv { grid-column: 2; } }
</style>
