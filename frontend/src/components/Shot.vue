<script setup>
// 真实截图：来自体验记录里该步骤操作前 / 操作后的页面截图（经校验的原始文件）。
import { ref, computed, watch } from 'vue'

const props = defineProps({
  step: { type: Object, required: true },
  device: String,
  time: String,
  live: Boolean,
  compact: Boolean, // 缩略图：不显示切换按钮
})
const which = ref('after')
watch(() => props.step, () => { which.value = 'after' })
const src = computed(() => props.step.shots?.[which.value] || props.step.shots?.after || props.step.shots?.before || null)
const hasBoth = computed(() => !props.compact && props.step.shots?.before && props.step.shots?.after && props.step.shots.before !== props.step.shots.after)
const m = computed(() => props.device === 'mobile')
const urlText = computed(() => props.step.url || props.step.path || '')
</script>

<template>
  <div class="shot" :class="{ m, live }">
    <div v-if="!compact" class="chrome">
      <span class="lights"><i></i><i></i><i></i></span>
      <span class="url"><span class="lock">⏺</span>{{ urlText }}</span>
      <span v-if="time" class="num tm">{{ time }}</span>
    </div>
    <div class="vp">
      <!-- 缩略图嵌在按钮里，不带链接，点击交给外层；完整视图里才能点开原图 -->
      <img v-if="src && compact" :src="src" :alt="`页面截图：${urlText}`" loading="lazy" />
      <a v-else-if="src" :href="src" target="_blank" rel="noopener" class="imglink" :aria-label="`在新标签打开原图：${urlText}`">
        <img :src="src" :alt="`页面截图（${which === 'before' ? '操作前' : '操作后'}）：${urlText}`" loading="lazy" />
      </a>
      <div v-else class="none">没有这一步的截图</div>
    </div>
    <div v-if="hasBoth" class="seg sw" role="group" aria-label="截图时点">
      <button type="button" :aria-pressed="which === 'before'" @click="which = 'before'">操作前</button>
      <button type="button" :aria-pressed="which === 'after'" @click="which = 'after'">操作后</button>
    </div>
  </div>
</template>

<style scoped>
.shot { border: 1px solid var(--border-strong); border-radius: var(--r-md); overflow: hidden; background: var(--surface); position: relative; }
.shot.live { box-shadow: 0 0 0 2px color-mix(in srgb, var(--sim) 35%, transparent); }
.chrome { display: flex; align-items: center; gap: var(--sp-3); padding: 6px var(--sp-3); background: var(--surface-2); border-bottom: 1px solid var(--border); font-size: var(--fs-xs); }
.lights { display: inline-flex; gap: 4px; flex: none; }
.lights i { width: 8px; height: 8px; border-radius: 50%; background: var(--border-strong); display: block; }
.url { flex: 1; min-width: 0; background: var(--bg); border-radius: var(--r-sm); padding: 1px var(--sp-2); color: var(--text-2); font-family: var(--font-mono); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.lock { color: var(--text-3); margin-right: 4px; font-size: 8px; }
.tm { color: var(--text-3); flex: none; }
.vp { background: var(--surface-2); }
.imglink { display: block; line-height: 0; }
img { width: 100%; height: auto; display: block; max-height: 520px; object-fit: cover; object-position: top; }
.none { padding: var(--sp-6); text-align: center; color: var(--text-3); font-size: var(--fs-sm); line-height: 1.5; }
.sw { position: absolute; right: var(--sp-2); bottom: var(--sp-2); box-shadow: var(--shadow-sm, 0 1px 4px rgba(0,0,0,.2)); }
</style>
