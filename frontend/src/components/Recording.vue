<script>
// 同一人物的录像信息在本页会话内只取一次（播放列表里的分段链接有效数小时）
const cache = new Map()
</script>

<script setup>
// Steel 录像片段：后端代取 HLS 播放列表（密钥不出服务器），按录像自带的时间戳把所引截图换算成播放位置，
// 从该时刻前 5 秒播到后 5 秒。取不到录像时退回估算秒数与 Steel 回放链接。
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { api } from '../api/client.js'
import { mmss } from '../lib/sim.js'

const props = defineProps({
  runId: { type: String, required: true },
  pid: { type: String, required: true },
  snapshot: String,
  estimate: { type: Number, default: 0 }, // 按会话创建时间估算的秒数，录像不可用时显示
})
const PAD = 5
const video = ref(null)
const state = ref('loading') // loading | ready | unavailable
const error = ref('')
const recording = ref(null)
const target = computed(() => recording.value?.seek?.[props.snapshot] ?? null)
let hls = null
let stopAt = null

function fetchRecording() {
  const key = `${props.runId}|${props.pid}`
  if (!cache.has(key)) cache.set(key, api.recording(props.runId, props.pid).catch((e) => { cache.delete(key); throw e }))
  return cache.get(key)
}

function seekToClip() {
  if (!video.value || target.value == null) return
  video.value.currentTime = Math.max(0, target.value - PAD)
  stopAt = target.value + PAD
}
function onTime() {
  if (stopAt != null && video.value.currentTime >= stopAt) { video.value.pause(); stopAt = null }
}

async function attach(url) {
  const { default: Hls } = await import('hls.js')
  if (Hls.isSupported()) {
    hls = new Hls()
    hls.on(Hls.Events.MANIFEST_PARSED, seekToClip)
    hls.on(Hls.Events.ERROR, (_, data) => { if (data.fatal) { state.value = 'unavailable'; error.value = `录像无法播放（${data.details}）` } })
    hls.loadSource(url)
    hls.attachMedia(video.value)
  } else if (video.value.canPlayType('application/vnd.apple.mpegurl')) {
    video.value.src = url
    video.value.addEventListener('loadedmetadata', seekToClip, { once: true })
  } else {
    state.value = 'unavailable'
    error.value = '这个浏览器不能播放 HLS 录像'
  }
}

async function load() {
  hls?.destroy()
  hls = null
  state.value = 'loading'
  try {
    recording.value = await fetchRecording()
    state.value = 'ready'
    await attach(recording.value.playlist_url)
  } catch (e) {
    state.value = 'unavailable'
    error.value = e.message
  }
}
watch(() => [props.runId, props.pid], load, { immediate: true })
watch(() => props.snapshot, seekToClip)
onBeforeUnmount(() => hls?.destroy())
</script>

<template>
  <div class="rec">
    <video v-show="state === 'ready'" ref="video" controls playsinline preload="metadata" @timeupdate="onTime"></video>
    <p v-if="state === 'ready' && target != null" class="faint note num">
      已定位到所引截图的时刻 {{ mmss(target) }}（录像时间戳对齐），播放 {{ mmss(Math.max(0, target - PAD)) }}–{{ mmss(target + PAD) }}。
      <button class="linkbtn" type="button" @click="seekToClip(); video.play()">重播片段</button>
    </p>
    <p v-else-if="state === 'ready'" class="faint note">所引截图不在录像范围内，录像从头播放。</p>
    <p v-else-if="state === 'loading'" class="faint note">正在读取录像…</p>
    <p v-else class="faint note num">录像不可用：{{ error }}。按会话创建时间估算，所引截图约在 {{ mmss(estimate) }}。</p>
  </div>
</template>

<style scoped>
.rec video { width: 100%; max-height: 360px; background: #000; border-radius: var(--r-md); display: block; }
.note { font-size: var(--fs-xs); margin: var(--sp-2) 0 0; line-height: 1.6; }
.linkbtn { border: none; background: none; padding: 0; color: var(--accent); cursor: pointer; font-size: inherit; }
</style>
