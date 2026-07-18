<template>
  <n-space vertical>
    <n-card title="系统设置">
      <n-h3>LLM 配置</n-h3>
      <n-p>当前 Provider: qwen3.7-max (通过 config.yaml 配置)</n-p>
      <n-h3>数据源</n-h3>
      <n-p>当前 Provider: akshare (免费)</n-p>
      <n-h3>回测摩擦成本</n-h3>
      <n-descriptions :column="2" bordered>
        <n-descriptions-item label="印花税">0.05%（卖出单边）</n-descriptions-item>
        <n-descriptions-item label="佣金">0.025%（买卖各）</n-descriptions-item>
        <n-descriptions-item label="最低佣金">5 元</n-descriptions-item>
        <n-descriptions-item label="滑点">0.1%</n-descriptions-item>
      </n-descriptions>
    </n-card>
  </n-space>
</template>

<script setup lang="ts">
</script>
