<template>
  <n-space vertical v-if="stock">
    <n-card :title="`${stock.name} (${stock.code})`">
      <n-descriptions :column="3" bordered>
        <n-descriptions-item label="市场">{{ stock.market }}</n-descriptions-item>
        <n-descriptions-item label="行业">{{ stock.industry || '-' }}</n-descriptions-item>
        <n-descriptions-item label="状态">{{ stock.is_active ? '活跃' : '停牌' }}</n-descriptions-item>
      </n-descriptions>
    </n-card>
    <n-card title="K线图">
      <v-chart :option="klineOption" style="height: 400px" autoresize />
    </n-card>
    <n-card title="财务数据">
      <n-data-table :columns="finColumns" :data="financials" :loading="finLoading" />
    </n-card>
  </n-space>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CandlestickChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, DataZoomComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { stocksApi } from '../api'
import type { Stock, DailyQuote } from '../types'

use([CandlestickChart, LineChart, GridComponent, TooltipComponent, DataZoomComponent, CanvasRenderer])

const route = useRoute()
const code = route.params.code as string
const stock = ref<Stock | null>(null)
const quotes = ref<DailyQuote[]>([])
const financials = ref<any[]>([])
const finLoading = ref(false)

const klineOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  xAxis: { type: 'category', data: quotes.value.map(q => q.date) },
  yAxis: { type: 'value', scale: true },
  dataZoom: [{ type: 'inside' }, { type: 'slider' }],
  series: [{
    type: 'candlestick',
    data: quotes.value.map(q => [q.open, q.close, q.low, q.high]),
  }],
}))

const finColumns = [
  { title: '报告期', key: 'report_date' },
  { title: '类型', key: 'report_type' },
  { title: '营收', key: 'revenue' },
  { title: '净利润', key: 'net_profit' },
  { title: 'ROE', key: 'roe' },
  { title: 'PE', key: 'pe_ratio' },
  { title: 'PB', key: 'pb_ratio' },
]

onMounted(async () => {
  const [stockRes, quotesRes] = await Promise.all([
    stocksApi.get(code),
    stocksApi.getQuotes(code, 120),
  ])
  stock.value = stockRes.data
  quotes.value = quotesRes.data

  finLoading.value = true
  try {
    const finRes = await stocksApi.getFinancials(code)
    financials.value = finRes.data
  } finally {
    finLoading.value = false
  }
})
</script>
