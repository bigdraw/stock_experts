<template>
  <n-space vertical>
    <n-card title="创建策略">
      <n-form>
        <n-form-item label="策略名称"><n-input v-model:value="name" /></n-form-item>
        <n-form-item label="自然语言描述">
          <n-input v-model:value="nlDesc" type="textarea" :rows="4" placeholder="例：均线交叉策略，5日均线上穿20日均线买入，下穿卖出" />
        </n-form-item>
        <n-button type="primary" :loading="generating" @click="handleGenerate">生成策略代码</n-button>
      </n-form>
    </n-card>

    <n-card title="执行回测" v-if="strategyId">
      <n-form inline>
        <n-form-item label="股票代码">
          <n-input v-model:value="stockCodes" placeholder="600519,000001" />
        </n-form-item>
        <n-form-item label="开始日期"><n-date-picker v-model:value="startDate" type="date" /></n-form-item>
        <n-form-item label="结束日期"><n-date-picker v-model:value="endDate" type="date" /></n-form-item>
        <n-form-item label="初始资金"><n-input-number v-model:value="capital" :min="10000" /></n-form-item>
        <n-button type="primary" :loading="running" @click="handleRun">执行回测</n-button>
      </n-form>
    </n-card>

    <n-card title="回测结果" v-if="result">
      <n-grid :cols="4" :x-gap="16">
        <n-gi><n-statistic label="总收益率" :value="(result.total_return * 100).toFixed(2) + '%'" /></n-gi>
        <n-gi><n-statistic label="最大回撤" :value="(result.max_drawdown * 100).toFixed(2) + '%'" /></n-gi>
        <n-gi><n-statistic label="夏普比率" :value="result.sharpe_ratio" /></n-gi>
        <n-gi><n-statistic label="胜率" :value="(result.win_rate * 100).toFixed(2) + '%'" /></n-gi>
      </n-grid>
      <v-chart v-if="result.equity_curve" :option="equityOption" style="height: 300px; margin-top: 16px" autoresize />
    </n-card>
  </n-space>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useMessage } from 'naive-ui'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { backtestApi } from '../api'
import type { BacktestResult } from '../types'

use([LineChart, GridComponent, TooltipComponent, CanvasRenderer])

const message = useMessage()
const name = ref('')
const nlDesc = ref('')
const generating = ref(false)
const strategyId = ref<number | null>(null)
const stockCodes = ref('600519')
const startDate = ref<number>(Date.now() - 365 * 24 * 3600 * 1000)
const endDate = ref<number>(Date.now())
const capital = ref(1000000)
const running = ref(false)
const result = ref<BacktestResult | null>(null)

const equityOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  xAxis: { type: 'category', data: result.value?.equity_curve?.map(e => e.date) || [] },
  yAxis: { type: 'value' },
  series: [{ type: 'line', data: result.value?.equity_curve?.map(e => e.value) || [], smooth: true }],
}))

function formatDate(ts: number) {
  return new Date(ts).toISOString().split('T')[0]
}

async function handleGenerate() {
  generating.value = true
  try {
    const res = await backtestApi.generate(name.value, nlDesc.value)
    strategyId.value = res.data.id
    message.success('策略代码已生成')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '生成失败')
  } finally {
    generating.value = false
  }
}

async function handleRun() {
  if (!strategyId.value) return
  running.value = true
  try {
    const codes = stockCodes.value.split(',').map(s => s.trim())
    const res = await backtestApi.run(strategyId.value, codes, formatDate(startDate.value), formatDate(endDate.value), capital.value)
    result.value = res.data
    message.success('回测完成')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '回测失败')
  } finally {
    running.value = false
  }
}
</script>
