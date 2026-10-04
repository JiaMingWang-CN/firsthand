<script setup>
// 人数用点阵 + 分数表示（设计语言第 13 节）
defineProps({ x: Number, y: Number, color: { type: String, default: 'var(--text)' }, showText: { type: Boolean, default: true } })
</script>

<template>
  <span class="dots" :aria-label="`${x}/${y}`">
    <span class="d" aria-hidden="true">
      <i v-for="i in y" :key="i" :class="{ on: i <= x }" :style="i <= x ? { background: color, borderColor: color } : {}"></i>
    </span>
    <span v-if="showText" class="num">{{ x }}/{{ y }}</span>
  </span>
</template>

<style scoped>
.dots { display: inline-flex; align-items: center; gap: var(--sp-2); }
.d { display: inline-flex; gap: 3px; }
i { width: 8px; height: 8px; border-radius: 50%; border: 1.5px solid var(--border-strong); display: block; }
.num { font-size: var(--fs-xs); color: var(--text-2); }
</style>
