<template>
  <n-space vertical>
    <n-card title="回测结果详情" v-if="result">
      <n-grid :cols="4" :x-gap="16">
        <n-gi><n-statistic label="总收益率" :value="(result.total_return * 100).toFixed(2) + '%'" /></n-gi>
        <n-gi><n-statistic label="年化收益率" :value="(result.annualized_return * 100).toFixed(2) + '%'" /></n-gi>
        <n-gi><n-statistic label="最大回撤" :value="(result.max_drawdown * 100).toFixed(2) + '%'" /></n-gi>
        <n-gi><n-statistic label="夏普比率" :value="result.sharpe_ratio" /></n-gi>
      </n-grid>
    </n-card>
    <n-empty v-else description="加载中..." />
  </n-space>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { backtestApi } from '../api'
import type { BacktestResult } from '../types'

const route = useRoute()
const result = ref<BacktestResult | null>(null)

onMounted(async () => {
  const res = await backtestApi.listResults()
  const id = Number(route.params.id)
  result.value = res.data.find(r => r.id === id) || null
})
</script>
