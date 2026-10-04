<script setup>
import { Info } from 'lucide-vue-next'
defineProps({ what: { type: String, default: '这个页面' } })
</script>

<template>
  <div class="note mock" role="note">
    <Info />
    <div><b>演示页面 · 未接入后端</b>：{{ what }}里的内容是演示数据，不会创建运行，也不会读取或写入真实的运行目录。目前运行由命令行（<span class="num">backend/orchestrator</span>）发起，这里只读取并展示已完成的运行。</div>
  </div>
</template>

<style scoped>
.mock { margin-bottom: var(--sp-5); }
</style>
