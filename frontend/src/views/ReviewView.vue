<script setup>
import MockNotice from '../components/MockNotice.vue'
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <div class="eyebrow">运行前审核</div>
        <h1 class="page-title">运行前审核</h1>
        <p class="page-sub">人物与运行配置在执行前需要人工确认。</p>
      </div>
    </header>
    <MockNotice what="运行前审核" />
    <div class="panel">
      <p>审核目前在命令行完成：<span class="num">orchestrator.phase1 review</span> 生成审核清单，确认后才会写入审批记录，之后才能运行浏览和讨论阶段。</p>
      <p class="faint">后续阶段会把审核搬到这里，并读写同一份审批记录。</p>
    </div>
  </div>
</template>
