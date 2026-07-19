<template>
  <div class="page-container" v-if="stock">
    <!-- 股票基本信息 -->
    <div class="page-header">
      <div class="header-left">
        <n-icon :size="32" color="#00d4aa">
          <TrendingUpOutline />
        </n-icon>
        <div>
          <h2 class="page-title gradient-text">{{ stock.name }}</h2>
          <div class="stock-code">{{ stock.code }}</div>
        </div>
      </div>
      <div class="header-right">
        <n-tag :type="stock.is_active ? 'success' : 'warning'" round size="large">
          <template #icon>
            <n-icon :size="14">
              <component :is="stock.is_active ? CheckmarkCircleOutline : PauseCircleOutline" />
            </n-icon>
          </template>
          {{ stock.is_active ? '交易中' : '停牌' }}
        </n-tag>
      </div>
    </div>

    <!-- 基本信息卡片 -->
    <n-grid :cols="4" :x-gap="16" :y-gap="16" class="info-grid">
      <n-gi>
        <div class="info-card info-card-primary">
          <div class="info-icon">
            <n-icon :size="24" color="#00d4aa">
              <BusinessOutline />
            </n-icon>
          </div>
          <div class="info-content">
            <div class="info-label">市场</div>
            <div class="info-value">{{ stock.market }}</div>
          </div>
        </div>
      </n-gi>
      <n-gi>
        <div class="info-card info-card-info">
          <div class="info-icon">
            <n-icon :size="24" color="#6366f1">
              <BriefcaseOutline />
            </n-icon>
          </div>
          <div class="info-content">
            <div class="info-label">行业</div>
            <div class="info-value">{{ stock.industry || '-' }}</div>
          </div>
        </div>
      </n-gi>
      <n-gi>
        <div class="info-card info-card-success">
          <div class="info-icon">
            <n-icon :size="24" color="#10b981">
              <LayersOutline />
            </n-icon>
          </div>
          <div class="info-content">
            <div class="info-label">板块</div>
            <div class="info-value">{{ stock.sector || '-' }}</div>
          </div>
        </div>
      </n-gi>
      <n-gi>
        <div class="info-card info-card-warning">
          <div class="info-icon">
            <n-icon :size="24" color="#f59e0b">
              <CalendarOutline />
            </n-icon>
          </div>
          <div class="info-content">
            <div class="info-label">上市日期</div>
            <div class="info-value">{{ stock.list_date || '-' }}</div>
          </div>
        </div>
      </n-gi>
    </n-grid>

    <!-- 实时行情指标 -->
    <n-card title="实时行情" class="data-card" v-if="latestQuote">
      <template #header-extra>
        <n-icon :size="20" color="#00d4aa">
          <PulseOutline />
        </n-icon>
      </template>
      <n-grid :cols="6" :x-gap="16" :y-gap="16">
        <n-gi>
          <div class="metric-box">
            <div class="metric-label">最新价</div>
            <div class="metric-value metric-value-primary">¥{{ formatNumber(latestQuote.close) }}</div>
          </div>
        </n-gi>
        <n-gi>
          <div class="metric-box">
            <div class="metric-label">开盘价</div>
            <div class="metric-value">¥{{ formatNumber(latestQuote.open) }}</div>
          </div>
        </n-gi>
        <n-gi>
          <div class="metric-box">
            <div class="metric-label">最高价</div>
            <div class="metric-value metric-value-success">¥{{ formatNumber(latestQuote.high) }}</div>
          </div>
        </n-gi>
        <n-gi>
          <div class="metric-box">
            <div class="metric-label">最低价</div>
            <div class="metric-value metric-value-error">¥{{ formatNumber(latestQuote.low) }}</div>
          </div>
        </n-gi>
        <n-gi>
          <div class="metric-box">
            <div class="metric-label">成交量</div>
            <div class="metric-value">{{ formatVolume(latestQuote.volume) }}</div>
          </div>
        </n-gi>
        <n-gi>
          <div class="metric-box">
            <div class="metric-label">成交额</div>
            <div class="metric-value">{{ formatAmount(latestQuote.amount) }}</div>
          </div>
        </n-gi>
      </n-grid>
      <n-grid :cols="3" :x-gap="16" :y-gap="16" style="margin-top: 16px;">
        <n-gi>
          <div class="metric-box">
            <div class="metric-label">换手率</div>
            <div class="metric-value">{{ latestQuote.turnover_rate ? (latestQuote.turnover_rate * 100).toFixed(2) + '%' : '-' }}</div>
          </div>
        </n-gi>
        <n-gi>
          <div class="metric-box">
            <div class="metric-label">振幅</div>
            <div class="metric-value">{{ calculateAmplitude(latestQuote) }}</div>
          </div>
        </n-gi>
        <n-gi>
          <div class="metric-box">
            <div class="metric-label">日期</div>
            <div class="metric-value">{{ latestQuote.date }}</div>
          </div>
        </n-gi>
      </n-grid>
    </n-card>

    <!-- K线图 -->
    <n-card title="K线图" class="chart-card">
      <template #header-extra>
        <n-icon :size="20" color="#6366f1">
          <TrendingUpOutline />
        </n-icon>
      </template>
      <v-chart :option="klineOption" style="height: 500px" autoresize />
    </n-card>

    <!-- 财务指标概览 -->
    <n-card title="财务指标概览" class="data-card" v-if="latestFinancial">
      <template #header-extra>
        <n-icon :size="20" color="#10b981">
          <AnalyticsOutline />
        </n-icon>
      </template>
      <n-grid :cols="4" :x-gap="16" :y-gap="16">
        <n-gi>
          <div class="metric-box metric-box-large">
            <div class="metric-label">市值</div>
            <div class="metric-value metric-value-primary">{{ formatMarketCap(latestFinancial.market_cap) }}</div>
          </div>
        </n-gi>
        <n-gi>
          <div class="metric-box metric-box-large">
            <div class="metric-label">市盈率 (PE)</div>
            <div class="metric-value">{{ latestFinancial.pe_ratio ? latestFinancial.pe_ratio.toFixed(2) : '-' }}</div>
          </div>
        </n-gi>
        <n-gi>
          <div class="metric-box metric-box-large">
            <div class="metric-label">市净率 (PB)</div>
            <div class="metric-value">{{ latestFinancial.pb_ratio ? latestFinancial.pb_ratio.toFixed(2) : '-' }}</div>
          </div>
        </n-gi>
        <n-gi>
          <div class="metric-box metric-box-large">
            <div class="metric-label">净资产收益率 (ROE)</div>
            <div class="metric-value">{{ latestFinancial.roe ? (latestFinancial.roe * 100).toFixed(2) + '%' : '-' }}</div>
          </div>
        </n-gi>
      </n-grid>
      <n-grid :cols="4" :x-gap="16" :y-gap="16" style="margin-top: 16px;">
        <n-gi>
          <div class="metric-box">
            <div class="metric-label">营业收入</div>
            <div class="metric-value">{{ formatAmount(latestFinancial.revenue) }}</div>
          </div>
        </n-gi>
        <n-gi>
          <div class="metric-box">
            <div class="metric-label">净利润</div>
            <div class="metric-value">{{ formatAmount(latestFinancial.net_profit) }}</div>
          </div>
        </n-gi>
        <n-gi>
          <div class="metric-box">
            <div class="metric-label">总资产</div>
            <div class="metric-value">{{ formatAmount(latestFinancial.total_assets) }}</div>
          </div>
        </n-gi>
        <n-gi>
          <div class="metric-box">
            <div class="metric-label">净资产</div>
            <div class="metric-value">{{ formatAmount(latestFinancial.total_equity) }}</div>
          </div>
        </n-gi>
      </n-grid>
      <n-grid :cols="2" :x-gap="16" :y-gap="16" style="margin-top: 16px;">
        <n-gi>
          <div class="metric-box">
            <div class="metric-label">是否盈利</div>
            <div class="metric-value">
              <n-tag :type="latestFinancial.is_profitable ? 'success' : 'error'" round>
                {{ latestFinancial.is_profitable ? '是' : '否' }}
              </n-tag>
            </div>
          </div>
        </n-gi>
        <n-gi>
          <div class="metric-box">
            <div class="metric-label">报告期</div>
            <div class="metric-value">{{ latestFinancial.report_date }} ({{ latestFinancial.report_type }})</div>
          </div>
        </n-gi>
      </n-grid>
    </n-card>

    <!-- 财务报表历史 -->
    <n-card title="财务报表历史" class="data-card">
      <template #header-extra>
        <n-icon :size="20" color="#f59e0b">
          <DocumentTextOutline />
        </n-icon>
      </template>
      <n-data-table 
        :columns="finColumns" 
        :data="financials" 
        :loading="finLoading"
        :bordered="false"
        :pagination="{ pageSize: 10 }"
      />
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CandlestickChart, LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, DataZoomComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { 
  TrendingUpOutline,
  CheckmarkCircleOutline,
  PauseCircleOutline,
  BusinessOutline,
  BriefcaseOutline,
  LayersOutline,
  CalendarOutline,
  PulseOutline,
  AnalyticsOutline,
  DocumentTextOutline
} from '@vicons/ionicons5'
import { stocksApi } from '../api'
import type { Stock, DailyQuote } from '../types'

use([CandlestickChart, LineChart, BarChart, GridComponent, TooltipComponent, DataZoomComponent, LegendComponent, CanvasRenderer])

const route = useRoute()
const code = computed(() => route.params.code as string)
const stock = ref<Stock | null>(null)
const quotes = ref<DailyQuote[]>([])
const financials = ref<any[]>([])
const finLoading = ref(false)

const latestQuote = computed(() => quotes.value.length > 0 ? quotes.value[quotes.value.length - 1] : null)
const latestFinancial = computed(() => financials.value.length > 0 ? financials.value[0] : null)

const klineOption = computed(() => ({
  tooltip: { 
    trigger: 'axis',
    axisPointer: { type: 'cross' },
    backgroundColor: 'rgba(15, 23, 42, 0.95)',
    borderColor: 'rgba(100, 116, 139, 0.3)',
    textStyle: { color: '#e2e8f0' }
  },
  legend: {
    data: ['K线', '成交量'],
    textStyle: { color: '#94a3b8' },
    top: 10
  },
  grid: [
    { left: '10%', right: '10%', top: '15%', height: '55%' },
    { left: '10%', right: '10%', top: '75%', height: '15%' }
  ],
  xAxis: [
    { 
      type: 'category', 
      data: quotes.value.map(q => q.date),
      gridIndex: 0,
      axisLine: { lineStyle: { color: 'rgba(100, 116, 139, 0.3)' } },
      axisLabel: { color: '#94a3b8' }
    },
    { 
      type: 'category', 
      data: quotes.value.map(q => q.date),
      gridIndex: 1,
      axisLine: { lineStyle: { color: 'rgba(100, 116, 139, 0.3)' } },
      axisLabel: { show: false }
    }
  ],
  yAxis: [
    { 
      type: 'value', 
      scale: true,
      gridIndex: 0,
      axisLine: { lineStyle: { color: 'rgba(100, 116, 139, 0.3)' } },
      axisLabel: { color: '#94a3b8' },
      splitLine: { lineStyle: { color: 'rgba(100, 116, 139, 0.1)' } }
    },
    { 
      type: 'value', 
      scale: true,
      gridIndex: 1,
      axisLine: { lineStyle: { color: 'rgba(100, 116, 139, 0.3)' } },
      axisLabel: { color: '#94a3b8' },
      splitLine: { show: false }
    }
  ],
  dataZoom: [
    { type: 'inside', xAxisIndex: [0, 1], start: 50, end: 100 },
    { type: 'slider', xAxisIndex: [0, 1], start: 50, end: 100, top: '93%' }
  ],
  series: [
    {
      name: 'K线',
      type: 'candlestick',
      data: quotes.value.map(q => [q.open, q.close, q.low, q.high]),
      xAxisIndex: 0,
      yAxisIndex: 0,
      itemStyle: {
        color: '#ef4444',
        color0: '#10b981',
        borderColor: '#ef4444',
        borderColor0: '#10b981'
      }
    },
    {
      name: '成交量',
      type: 'bar',
      data: quotes.value.map(q => q.volume),
      xAxisIndex: 1,
      yAxisIndex: 1,
      itemStyle: {
        color: (params: any) => {
          const quote = quotes.value[params.dataIndex]
          return quote.close >= quote.open ? '#ef4444' : '#10b981'
        }
      }
    }
  ]
}))

const finColumns = [
  { 
    title: '报告期', 
    key: 'report_date',
    width: 120,
    render: (row: any) => h('span', { style: 'font-weight: 600; color: var(--text-primary);' }, row.report_date)
  },
  { 
    title: '类型', 
    key: 'report_type',
    width: 100,
    render: (row: any) => h(NTag, { size: 'small', type: 'info', round: true }, { default: () => row.report_type })
  },
  { 
    title: '营收', 
    key: 'revenue',
    render: (row: any) => h('span', { style: 'color: var(--text-secondary);' }, formatAmount(row.revenue))
  },
  { 
    title: '净利润', 
    key: 'net_profit',
    render: (row: any) => h('span', { style: 'color: var(--text-secondary);' }, formatAmount(row.net_profit))
  },
  { 
    title: '总资产', 
    key: 'total_assets',
    render: (row: any) => h('span', { style: 'color: var(--text-secondary);' }, formatAmount(row.total_assets))
  },
  { 
    title: '净资产', 
    key: 'total_equity',
    render: (row: any) => h('span', { style: 'color: var(--text-secondary);' }, formatAmount(row.total_equity))
  },
  { 
    title: 'ROE', 
    key: 'roe',
    render: (row: any) => h('span', { style: 'color: var(--text-secondary);' }, row.roe ? (row.roe * 100).toFixed(2) + '%' : '-')
  },
  { 
    title: 'PE', 
    key: 'pe_ratio',
    render: (row: any) => h('span', { style: 'color: var(--text-secondary);' }, row.pe_ratio ? row.pe_ratio.toFixed(2) : '-')
  },
  { 
    title: 'PB', 
    key: 'pb_ratio',
    render: (row: any) => h('span', { style: 'color: var(--text-secondary);' }, row.pb_ratio ? row.pb_ratio.toFixed(2) : '-')
  },
  { 
    title: '市值', 
    key: 'market_cap',
    render: (row: any) => h('span', { style: 'color: var(--text-secondary);' }, formatMarketCap(row.market_cap))
  },
]

function formatNumber(num: number | null | undefined): string {
  if (num === null || num === undefined) return '-'
  return num.toFixed(2)
}

function formatVolume(volume: number | null | undefined): string {
  if (volume === null || volume === undefined) return '-'
  if (volume >= 100000000) return (volume / 100000000).toFixed(2) + '亿'
  if (volume >= 10000) return (volume / 10000).toFixed(2) + '万'
  return volume.toFixed(0)
}

function formatAmount(amount: number | null | undefined): string {
  if (amount === null || amount === undefined) return '-'
  if (amount >= 100000000) return '¥' + (amount / 100000000).toFixed(2) + '亿'
  if (amount >= 10000) return '¥' + (amount / 10000).toFixed(2) + '万'
  return '¥' + amount.toFixed(2)
}

function formatMarketCap(cap: number | null | undefined): string {
  if (cap === null || cap === undefined) return '-'
  if (cap >= 100000000) return '¥' + (cap / 100000000).toFixed(2) + '亿'
  if (cap >= 10000) return '¥' + (cap / 10000).toFixed(2) + '万'
  return '¥' + cap.toFixed(2)
}

function calculateAmplitude(quote: DailyQuote): string {
  if (!quote.high || !quote.low || !quote.open) return '-'
  const amplitude = ((quote.high - quote.low) / quote.open) * 100
  return amplitude.toFixed(2) + '%'
}

async function loadData(stockCode: string) {
  stock.value = null
  quotes.value = []
  financials.value = []
  
  const [stockRes, quotesRes] = await Promise.all([
    stocksApi.get(stockCode),
    stocksApi.getQuotes(stockCode, 120),
  ])
  stock.value = stockRes.data
  quotes.value = quotesRes.data

  finLoading.value = true
  try {
    const finRes = await stocksApi.getFinancials(stockCode)
    financials.value = finRes.data
  } finally {
    finLoading.value = false
  }
}

onMounted(() => {
  loadData(code.value)
})

watch(code, (newCode) => {
  if (newCode) {
    loadData(newCode)
  }
})
</script>

<style scoped>
.page-container {
  animation: fadeIn 0.3s ease-out;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 2px solid var(--border-subtle);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.page-title {
  font-size: 32px;
  font-weight: 700;
  margin: 0;
  letter-spacing: -0.5px;
}

.stock-code {
  font-size: 14px;
  color: var(--text-tertiary);
  margin-top: 4px;
  font-weight: 500;
}

.info-grid {
  margin-bottom: 24px;
}

.info-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
  border-radius: 12px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  transition: all 0.3s;
  position: relative;
  overflow: hidden;
}

.info-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  opacity: 0.8;
}

.info-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
}

.info-card-primary::before {
  background: linear-gradient(90deg, #00d4aa, transparent);
}

.info-card-info::before {
  background: linear-gradient(90deg, #6366f1, transparent);
}

.info-card-success::before {
  background: linear-gradient(90deg, #10b981, transparent);
}

.info-card-warning::before {
  background: linear-gradient(90deg, #f59e0b, transparent);
}

.info-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: rgba(30, 41, 59, 0.6);
}

.info-content {
  flex: 1;
}

.info-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 4px;
}

.info-value {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
}

.data-card,
.chart-card {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 12px !important;
  margin-bottom: 20px;
  transition: all 0.3s;
}

.data-card:hover,
.chart-card:hover {
  border-color: var(--border-medium) !important;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
}

.data-card :deep(.n-card-header),
.chart-card :deep(.n-card-header) {
  border-bottom: 1px solid var(--border-subtle);
}

.data-card :deep(.n-card-header__main),
.chart-card :deep(.n-card-header__main) {
  font-weight: 600;
  font-size: 18px;
  color: var(--text-primary);
}

.metric-box {
  padding: 16px;
  border-radius: 8px;
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid var(--border-subtle);
  transition: all 0.3s;
}

.metric-box:hover {
  border-color: var(--border-medium);
  background: rgba(30, 41, 59, 0.8);
}

.metric-box-large {
  padding: 20px;
}

.metric-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}

.metric-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1;
}

.metric-value-primary {
  background: linear-gradient(135deg, #00d4aa, #6366f1);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.metric-value-success {
  color: #10b981;
}

.metric-value-error {
  color: #ef4444;
}

.data-card :deep(.n-data-table) {
  background: transparent !important;
}

.data-card :deep(.n-data-table-thead) {
  background: rgba(30, 41, 59, 0.6) !important;
}

.data-card :deep(.n-data-table-th) {
  background: transparent !important;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  font-size: 12px;
  letter-spacing: 0.5px;
}

.data-card :deep(.n-data-table-td) {
  border-bottom: 1px solid var(--border-subtle) !important;
  transition: all 0.2s;
}

.data-card :deep(.n-data-table-tr:hover .n-data-table-td) {
  background: rgba(0, 212, 170, 0.05) !important;
}

.data-card :deep(.n-data-table-tr:hover .n-data-table-td::before) {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: linear-gradient(180deg, #00d4aa 0%, #6366f1 100%);
  animation: slideIn 0.2s ease-out;
}

@keyframes slideIn {
  from {
    transform: scaleY(0);
  }
  to {
    transform: scaleY(1);
  }
}

.data-card :deep(.n-data-table-tr:nth-child(even) .n-data-table-td) {
  background: rgba(30, 41, 59, 0.3);
}
</style>
