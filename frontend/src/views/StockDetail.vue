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
    <n-card title="实时行情" class="data-card" v-if="latestIndicators">
      <template #header-extra>
        <n-icon :size="20" color="#00d4aa">
          <PulseOutline />
        </n-icon>
      </template>
      <n-grid :cols="6" :x-gap="16" :y-gap="16">
        <n-gi>
          <div class="metric-box">
            <div class="metric-label">最新价</div>
            <div class="metric-value metric-value-primary">¥{{ formatNumber(latestIndicators.price) }}</div>
          </div>
        </n-gi>
        <n-gi>
          <div class="metric-box">
            <div class="metric-label">涨跌幅</div>
            <div class="metric-value" :class="latestIndicators.changepercent > 0 ? 'metric-value-error' : latestIndicators.changepercent < 0 ? 'metric-value-success' : ''">
              {{ latestIndicators.changepercent != null ? (latestIndicators.changepercent > 0 ? '+' : '') + latestIndicators.changepercent.toFixed(2) + '%' : '-' }}
            </div>
          </div>
        </n-gi>
        <n-gi>
          <div class="metric-box">
            <div class="metric-label">开盘价</div>
            <div class="metric-value">¥{{ formatNumber(latestIndicators.open) }}</div>
          </div>
        </n-gi>
        <n-gi>
          <div class="metric-box">
            <div class="metric-label">最高价</div>
            <div class="metric-value metric-value-success">¥{{ formatNumber(latestIndicators.high) }}</div>
          </div>
        </n-gi>
        <n-gi>
          <div class="metric-box">
            <div class="metric-label">最低价</div>
            <div class="metric-value" style="color: #ef4444;">¥{{ formatNumber(latestIndicators.low) }}</div>
          </div>
        </n-gi>
        <n-gi>
          <div class="metric-box">
            <div class="metric-label">昨收价</div>
            <div class="metric-value">¥{{ formatNumber(latestIndicators.settlement) }}</div>
          </div>
        </n-gi>
      </n-grid>
      <n-grid :cols="6" :x-gap="16" :y-gap="16" style="margin-top: 16px;">
        <n-gi>
          <div class="metric-box">
            <div class="metric-label">成交量</div>
            <div class="metric-value">{{ formatVolume(latestIndicators.volume) }}</div>
          </div>
        </n-gi>
        <n-gi>
          <div class="metric-box">
            <div class="metric-label">成交额</div>
            <div class="metric-value">{{ formatAmount(latestIndicators.amount) }}</div>
          </div>
        </n-gi>
        <n-gi>
          <div class="metric-box">
            <div class="metric-label">换手率</div>
            <div class="metric-value">{{ latestIndicators.turnoverratio ? latestIndicators.turnoverratio.toFixed(2) + '%' : '-' }}</div>
          </div>
        </n-gi>
        <n-gi>
          <div class="metric-box">
            <div class="metric-label">总市值</div>
            <div class="metric-value">{{ formatMarketCap(latestIndicators.mktcap) }}</div>
          </div>
        </n-gi>
        <n-gi>
          <div class="metric-box">
            <div class="metric-label">流通市值</div>
            <div class="metric-value">{{ formatMarketCap(latestIndicators.nmc) }}</div>
          </div>
        </n-gi>
        <n-gi>
          <div class="metric-box">
            <div class="metric-label">日期</div>
            <div class="metric-value">{{ latestIndicators.report_date }}</div>
          </div>
        </n-gi>
      </n-grid>
    </n-card>

    <!-- 价值投资分析（复用缓存财报 + 三大报表） -->
    <n-card v-if="valueAnalysis && !valueAnalysis.error" class="data-card">
      <template #header>
        <span style="font-weight: 600; color: var(--text-primary);">价值投资分析</span>
        <span style="font-size: 11px; color: var(--text-tertiary); margin-left: 8px;">
          最新期 {{ valueAnalysis.latest?.report_date }}
        </span>
      </template>
      <n-grid :cols="4" :x-gap="16" :y-gap="16">
        <!-- 估值 -->
        <n-gi>
          <div class="value-section">
            <div class="value-section-title">估值</div>
            <div class="value-row"><span>PE</span><b>{{ fmtNum(valueAnalysis.valuation?.pe) }}</b></div>
            <div class="value-row"><span>PB</span><b>{{ fmtNum(valueAnalysis.valuation?.pb) }}</b></div>
            <div class="value-row"><span>PS</span><b>{{ fmtNum(valueAnalysis.valuation?.ps) }}</b></div>
            <div class="value-row"><span>PCF</span><b>{{ fmtNum(valueAnalysis.valuation?.pcf) }}</b></div>
            <div class="value-row"><span>Graham估值</span><b>¥{{ fmtNum(valueAnalysis.valuation?.graham_number) }}</b></div>
            <div class="value-row"><span>股息率</span><b>{{ fmtPct(valueAnalysis.valuation?.dividend_yield) }}</b></div>
          </div>
        </n-gi>
        <!-- 盈利能力 -->
        <n-gi>
          <div class="value-section">
            <div class="value-section-title">盈利能力</div>
            <div class="value-row"><span>ROE</span><b>{{ fmtPct(valueAnalysis.latest?.roe) }}</b></div>
            <div class="value-row"><span>ROA</span><b>{{ fmtPct(valueAnalysis.latest?.roa) }}</b></div>
            <div class="value-row"><span>ROIC</span><b>{{ fmtPct(valueAnalysis.latest?.roic) }}</b></div>
            <div class="value-row"><span>毛利率</span><b>{{ fmtPct(valueAnalysis.latest?.gross_margin) }}</b></div>
            <div class="value-row"><span>净利率</span><b>{{ fmtPct(valueAnalysis.latest?.net_margin) }}</b></div>
          </div>
        </n-gi>
        <!-- 财务安全 -->
        <n-gi>
          <div class="value-section">
            <div class="value-section-title">财务安全</div>
            <div class="value-row"><span>资产负债率</span><b>{{ fmtPct(valueAnalysis.latest?.debt_ratio) }}</b></div>
            <div class="value-row"><span>流动比率</span><b>{{ fmtNum(valueAnalysis.latest?.current_ratio, 2) }}</b></div>
            <div class="value-row"><span>现金比率</span><b>{{ fmtNum(valueAnalysis.latest?.cash_ratio, 2) }}</b></div>
            <div class="value-row"><span>利息保障</span><b>{{ fmtNum(valueAnalysis.latest?.interest_coverage, 1) }}</b></div>
          </div>
        </n-gi>
        <!-- 现金流 -->
        <n-gi>
          <div class="value-section">
            <div class="value-section-title">现金流</div>
            <div class="value-row"><span>经营现金流</span><b>{{ formatAmount(valueAnalysis.latest?.ocf) }}</b></div>
            <div class="value-row"><span>自由现金流</span><b>{{ formatAmount(valueAnalysis.latest?.fcf) }}</b></div>
            <div class="value-row"><span>FCF收益率</span><b>{{ fmtPct(valueAnalysis.valuation?.fcf_yield) }}</b></div>
            <div class="value-row"><span>盈利质量(OCF/净利)</span><b>{{ fmtNum(valueAnalysis.latest?.earnings_quality, 2) }}</b></div>
          </div>
        </n-gi>
      </n-grid>

      <!-- 关键指标历史均值（近3年/近10年，不满10年标*） -->
      <div v-if="Object.keys(metricStats).length" class="stats-bar">
        <span class="stats-label">历史均值：</span>
        <span class="stats-item" v-for="(s, k) in metricStats" :key="k">
          {{ k === 'eps' ? 'EPS' : k === 'roe' ? 'ROE' : k === 'gross_margin' ? '毛利率' : k === 'net_margin' ? '净利率' : '负债率' }}：
          <b>3y {{ s.avg3 !== null ? fmtStat(s.avg3) : '-' }}</b>
          <b>10y {{ s.avg10 !== null ? fmtStat(s.avg10) : '-' }}{{ s.has10y ? '' : '*' }}</b>
        </span>
      </div>

      <n-grid :cols="3" :x-gap="16" :y-gap="16" style="margin-top: 16px;">
        <!-- 成长性 -->
        <n-gi>
          <div class="value-section">
            <div class="value-section-title">成长性 (CAGR)</div>
            <div class="value-row"><span>营收 3年/5年</span><b>{{ fmtPct(valueAnalysis.growth?.revenue?.cagr_3y) }} / {{ fmtPct(valueAnalysis.growth?.revenue?.cagr_5y) }}</b></div>
            <div class="value-row"><span>净利 3年/5年</span><b>{{ fmtPct(valueAnalysis.growth?.net_profit?.cagr_3y) }} / {{ fmtPct(valueAnalysis.growth?.net_profit?.cagr_5y) }}</b></div>
            <div class="value-row"><span>净资产 3年/5年</span><b>{{ fmtPct(valueAnalysis.growth?.equity?.cagr_3y) }} / {{ fmtPct(valueAnalysis.growth?.equity?.cagr_5y) }}</b></div>
            <div class="value-row"><span>年报数</span><b>{{ valueAnalysis.annual_count }}</b></div>
          </div>
        </n-gi>
        <!-- 分红记录 -->
        <n-gi :span="2">
          <div class="value-section">
            <div class="value-section-title">分红记录 (近 {{ valueAnalysis.dividends?.length || 0 }} 次)</div>
            <n-data-table
              :columns="dividendColumns"
              :data="valueAnalysis.dividends || []"
              :bordered="false"
              :pagination="{ pageSize: 5 }"
              size="small"
            />
          </div>
        </n-gi>
      </n-grid>
    </n-card>

    <!-- K线图 -->
    <n-card class="chart-card">
      <template #header>
        <span style="font-weight: 600; color: var(--text-primary);">K线图</span>
      </template>
      <template #header-extra>
        <n-space align="center" :size="8">
          <n-radio-group v-model:value="klinePeriod" size="small" @update:value="onPeriodChange">
            <n-radio-button value="daily">日K</n-radio-button>
            <n-radio-button value="weekly">周K</n-radio-button>
            <n-radio-button value="monthly">月K</n-radio-button>
            <n-radio-button value="quarterly">季K</n-radio-button>
            <n-radio-button value="yearly">年K</n-radio-button>
          </n-radio-group>
          <n-icon :size="20" color="#6366f1">
            <TrendingUpOutline />
          </n-icon>
        </n-space>
      </template>
      <n-spin :show="klineLoading" description="加载K线…">
        <v-chart :option="klineOption" style="height: 500px" autoresize />
      </n-spin>
    </n-card>

    <!-- 财务趋势分析 -->
    <n-card v-if="periodicSorted.length > 0" class="data-card">
      <template #header>
        <span style="font-weight: 600; color: var(--text-primary);">财务趋势分析</span>
      </template>
      <template #header-extra>
        <n-icon :size="20" color="#00d4aa">
          <AnalyticsOutline />
        </n-icon>
      </template>
      <n-grid :cols="2" :x-gap="16" :y-gap="16">
        <n-gi>
          <div class="trend-block">
            <div class="trend-title">ROE 趋势</div>
            <v-chart :option="roeTrendOption" style="height: 280px" autoresize />
          </div>
        </n-gi>
        <n-gi>
          <div class="trend-block">
            <div class="trend-title">营收与净利润</div>
            <v-chart :option="revenueProfitTrendOption" style="height: 280px" autoresize />
          </div>
        </n-gi>
        <n-gi>
          <div class="trend-block">
            <div class="trend-title">利润率趋势</div>
            <v-chart :option="marginTrendOption" style="height: 280px" autoresize />
          </div>
        </n-gi>
        <n-gi>
          <div class="trend-block">
            <div class="trend-title">
              <n-radio-group v-model:value="bandType" size="tiny">
                <n-radio-button value="pe">P/E</n-radio-button>
                <n-radio-button value="pb">P/B</n-radio-button>
                <n-radio-button value="ps">P/S</n-radio-button>
              </n-radio-group>
              估值带（均值黄虚线 · 30/70 分位）
            </div>
            <v-chart :option="bandOption" style="height: 280px" autoresize />
          </div>
        </n-gi>
      </n-grid>
    </n-card>

    <!-- 财务报表历史 -->
    <n-card class="data-card">
      <template #header>
        <span style="font-weight: 600; color: var(--text-primary);">财务报表历史</span>
      </template>
      <template #header-extra>
        <n-space align="center" :size="12">
          <n-radio-group v-model:value="finFilter" size="small">
            <n-radio-button value="all">全部</n-radio-button>
            <n-radio-button value="Annual">年报</n-radio-button>
            <n-radio-button value="H1">中报</n-radio-button>
            <n-radio-button value="Q1">一季</n-radio-button>
            <n-radio-button value="Q3">三季</n-radio-button>
          </n-radio-group>
          <n-icon :size="20" color="#f59e0b">
            <DocumentTextOutline />
          </n-icon>
        </n-space>
      </template>
      <n-data-table
        :columns="finColumns"
        :data="filteredFinancials"
        :loading="finLoading"
        :bordered="false"
        :pagination="{ pageSize: 10 }"
      />
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, h, onMounted, computed, watch, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { NTag } from 'naive-ui'
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
const latestIndicators = ref<any>(null)
const finLoading = ref(false)
const klineLoading = ref(false)
const klinePeriod = ref<string>('daily')
const finFilter = ref<string>('all') // all | Annual | H1 | Q1 | Q3
const valueAnalysis = ref<any>(null)
const bandType = ref<'pe' | 'pb' | 'ps'>('pe')

// 关键指标的 近3年/近10年 均值（从年报计算，不满10年标注 *）
const metricStats = computed(() => {
  const annuals = financials.value
    .filter(f => f.report_type === 'Annual')
    .slice()
    .sort((a, b) => (a.report_date > b.report_date ? -1 : 1)) // 降序
  const stats: Record<string, { avg3: number | null; avg10: number | null; has10y: boolean }> = {}
  const fields = ['roe', 'gross_margin', 'net_margin', 'debt_ratio', 'eps']
  for (const f of fields) {
    const vals3 = annuals.slice(0, 3).map(r => r[f]).filter(v => v != null)
    const vals10 = annuals.slice(0, 10).map(r => r[f]).filter(v => v != null)
    stats[f] = {
      avg3: vals3.length >= 3 ? vals3.reduce((s, v) => s + v, 0) / vals3.length : null,
      avg10: vals10.length >= 3 ? vals10.reduce((s, v) => s + v, 0) / vals10.length : null,
      has10y: vals10.length >= 10,
    }
  }
  return stats
})

function fmtStat(v: number | null | undefined): string {
  if (v === null || v === undefined) return '-'
  return (v * 100).toFixed(1) + '%'
}

const latestQuote = computed(() => quotes.value.length > 0 ? quotes.value[quotes.value.length - 1] : null)
const latestFinancial = computed(() => {
  // Pick the most recent non-'Latest' (actual quarterly/annual) report by date.
  // Previously used .find() which returned the first array element regardless of
  // ordering, so a stale report could be shown.
  const periodic = financials.value.filter(f => f.report_type && f.report_type !== 'Latest')
  if (periodic.length === 0) return null
  return periodic.reduce((a, b) => (a.report_date > b.report_date ? a : b))
})

// 财报表按报告类型过滤（并排除 'Latest' 快照脏行）
const filteredFinancials = computed(() => {
  const periodic = financials.value.filter(f => f.report_type && f.report_type !== 'Latest')
  if (finFilter.value === 'all') return periodic
  return periodic.filter(f => f.report_type === finFilter.value)
})

// 同比 (YoY) 查找：按 report_date 取该期一年前同期（同 report_type）算各指标同比 %
const yoyLookup = computed(() => {
  const periodic = financials.value.filter(f => f.report_type && f.report_type !== 'Latest')
  // key: report_type + year -> row
  const byTypeYear = new Map<string, any>()
  for (const r of periodic) {
    const y = (r.report_date || '').slice(0, 4)
    if (y) byTypeYear.set(`${r.report_type}_${y}`, r)
  }
  const out: Record<string, Record<string, number | null>> = {}
  for (const r of periodic) {
    const y = parseInt((r.report_date || '').slice(0, 4), 10)
    if (!y) continue
    const prior = byTypeYear.get(`${r.report_type}_${y - 1}`)
    if (!prior) { out[r.report_date] = {}; continue }
    const yoy = (k: string) => {
      const c = r[k], p = prior[k]
      if (c == null || p == null || p === 0) return null
      return (c - p) / Math.abs(p)
    }
    out[r.report_date] = {
      revenue: yoy('revenue'), net_profit: yoy('net_profit'), roe: yoy('roe'),
      eps: yoy('eps'), gross_margin: yoy('gross_margin'), net_margin: yoy('net_margin'),
      bps: yoy('bps'), debt_ratio: yoy('debt_ratio'),
    }
  }
  return out
})

// 指标单元格：值 + 同比（小字、绿涨红跌）
function metricCell(row: any, key: string, fmt: (v: number) => string) {
  const yoyMap = yoyLookup.value[row.report_date] || {}
  const yoy = yoyMap[key]
  const color = yoy == null ? 'var(--text-tertiary)' : yoy > 0 ? '#10b981' : yoy < 0 ? '#ef4444' : 'var(--text-tertiary)'
  const yoyStr = yoy == null ? '' : (yoy > 0 ? '+' : '') + (yoy * 100).toFixed(1) + '% 同比'
  return h('div', { style: 'line-height: 1.3;' }, [
    h('div', { style: 'color: var(--text-secondary);' }, fmt(row[key])),
    h('div', { style: `font-size: 11px; color: ${color};` }, yoyStr),
  ])
}

// 周期财报按日期升序（趋势图用）
const periodicSorted = computed(() => {
  return financials.value
    .filter(f => f.report_type && f.report_type !== 'Latest')
    .slice()
    .sort((a, b) => (a.report_date > b.report_date ? 1 : -1))
})

// ROE 趋势线
const roeTrendOption = computed(() => {
  const data = periodicSorted.value
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: '8%', right: '5%', top: '15%', bottom: '18%' },
    xAxis: { type: 'category', data: data.map(d => d.report_date), axisLabel: { rotate: 40, color: '#94a3b8' } },
    yAxis: { type: 'value', name: 'ROE %', axisLabel: { color: '#94a3b8', formatter: (v: number) => (v * 100).toFixed(1) + '%' } },
    series: [{
      name: 'ROE', type: 'line', smooth: true, symbol: 'circle', symbolSize: 6,
      data: data.map(d => d.roe),
      itemStyle: { color: '#00d4aa' }, areaStyle: { color: 'rgba(0,212,170,0.12)' },
    }],
  }
})

// 营收 + 净利 趋势（双柱+双轴+增长率折线）
const revenueProfitTrendOption = computed(() => {
  const data = periodicSorted.value
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['营业收入', '净利润', '营收增长', '净利增长'], textStyle: { color: '#94a3b8' }, top: 5 },
    grid: { left: '8%', right: '12%', top: '18%', bottom: '18%' },
    xAxis: { type: 'category', data: data.map(d => d.report_date), axisLabel: { rotate: 40, color: '#94a3b8' } },
    yAxis: [
      { type: 'value', name: '营收', axisLabel: { color: '#94a3b8', formatter: (v: number) => (v >= 1e8 ? (v / 1e8).toFixed(1) + '亿' : v.toFixed(0)) } },
      { type: 'value', name: '净利', axisLabel: { color: '#94a3b8', formatter: (v: number) => (v >= 1e8 ? (v / 1e8).toFixed(1) + '亿' : v.toFixed(0)) } },
      { type: 'value', name: '增长率%', axisLabel: { color: '#94a3b8', formatter: (v: number) => v.toFixed(0) + '%' } },
    ],
    series: [
      { name: '营业收入', type: 'bar', data: data.map(d => d.revenue), itemStyle: { color: '#6366f1' } },
      { name: '净利润', type: 'bar', data: data.map(d => d.net_profit), itemStyle: { color: '#00d4aa' }, yAxisIndex: 1 },
      { name: '营收增长', type: 'line', smooth: true, yAxisIndex: 2, data: data.map(d => (d.revenue_growth ?? 0) * 100), itemStyle: { color: '#f59e0b' }, lineStyle: { width: 1.5 } },
      { name: '净利增长', type: 'line', smooth: true, yAxisIndex: 2, data: data.map(d => (d.net_profit_growth ?? 0) * 100), itemStyle: { color: '#ef4444' }, lineStyle: { width: 1.5 } },
    ],
  }
})

// 毛利率 + 净利率 趋势线
const marginTrendOption = computed(() => {
  const data = periodicSorted.value
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['销售毛利率', '销售净利率'], textStyle: { color: '#94a3b8' }, top: 5 },
    grid: { left: '8%', right: '5%', top: '18%', bottom: '18%' },
    xAxis: { type: 'category', data: data.map(d => d.report_date), axisLabel: { rotate: 40, color: '#94a3b8' } },
    yAxis: { type: 'value', axisLabel: { color: '#94a3b8', formatter: (v: number) => (v * 100).toFixed(0) + '%' } },
    series: [
      { name: '销售毛利率', type: 'line', smooth: true, data: data.map(d => d.gross_margin), itemStyle: { color: '#f59e0b' } },
      { name: '销售净利率', type: 'line', smooth: true, data: data.map(d => d.net_margin), itemStyle: { color: '#10b981' } },
    ],
  }
})

// 估值带（P/E / P/B / P/S 切换）：日K收盘 / 锚定值，叠加均值 + 30/70 分位带
const bandOption = computed(() => {
  const q = quotes.value
  if (!q || q.length < 30) return {}
  const lf = latestFinancial.value
  const li = latestIndicators.value

  let anchor = 0  // 分母：EPS(BPS/年化营收)
  let label = 'PE'
  if (bandType.value === 'pe') {
    label = 'PE'
    if (lf && lf.eps) {
      anchor = lf.report_type === 'Annual' ? lf.eps
        : lf.report_type === 'H1' ? lf.eps * 2
        : lf.report_type === 'Q3' ? lf.eps * 4 / 3
        : lf.eps * 4
    } else if (li && li.per && li.price) {
      anchor = li.price / li.per
    }
  } else if (bandType.value === 'pb') {
    label = 'PB'
    anchor = lf?.bps || 0
  } else if (bandType.value === 'ps') {
    label = 'PS'
    // PS = 市值 / 年化营收；用 close / (年化营收/总股本) 简化为 close*总股本/年化营收
    // 但没有总股本 → 用 close / (年化营收 / 市值) = close * 市值 / 年化营收，太绕
    // 简化：用最新 PS 锚 = 市值/年化营收，则 PS_t = close_t * (市值_最新/close_最新) / 年化营收
    if (li && li.mktcap && li.price && lf && lf.revenue) {
      const mktcap = li.mktcap * 10000  // 万元→元
      const rd = lf.report_date
      const annRev = lf.revenue * (rd.endsWith('12-31') ? 1 : rd.endsWith('03-31') ? 4 : rd.endsWith('06-30') ? 2 : 4/3)
      if (annRev > 0) anchor = li.price / (mktcap / annRev)  // 反推每股营收
    }
  }
  if (anchor <= 0) return {}

  const series = q.map(bar => [bar.date, bar.close / anchor])
  const vals = series.map(p => p[1]).filter(v => v > 0).sort((a, b) => a - b)
  if (vals.length < 30) return {}
  const pct = (p: number) => vals[Math.floor(p * vals.length)] || vals[vals.length - 1]
  const avg = vals.reduce((s, v) => s + v, 0) / vals.length
  return {
    tooltip: { trigger: 'axis', formatter: (params: any) => {
      const d = params[0]
      return `${d.axisValue}<br/>${label}: ${d.value != null ? d.value.toFixed(2) : '-'}<br/>均值: ${avg.toFixed(2)}`
    } },
    legend: { data: [label, '均值'], textStyle: { color: '#94a3b8' }, top: 5 },
    grid: { left: '8%', right: '5%', top: '18%', bottom: '18%' },
    xAxis: { type: 'category', data: series.map(p => p[0]), axisLabel: { color: '#94a3b8' } },
    yAxis: { type: 'value', name: label, axisLabel: { color: '#94a3b8' } },
    dataZoom: [{ type: 'inside' }],
    series: [
      {
        name: label, type: 'line', smooth: true, symbol: 'none',
        data: series.map(p => p[1]),
        itemStyle: { color: '#6366f1' }, lineStyle: { width: 1.2 },
        markLine: { silent: true, symbol: 'none', lineStyle: { color: '#f59e0b', type: 'dashed' },
          data: [{ yAxis: avg }, { yAxis: pct(0.3), lineStyle: { color: '#10b981' } }, { yAxis: pct(0.7), lineStyle: { color: '#ef4444' } }] },
      },
    ],
  }
})

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
          return (quote.close ?? 0) >= (quote.open ?? 0) ? '#ef4444' : '#10b981'
        }
      }
    }
  ]
}))

const finColumns = [
  {
    title: '报告期',
    key: 'report_date',
    width: 110,
    fixed: 'left' as const,
    render: (row: any) => h('span', { style: 'font-weight: 600; color: var(--text-primary);' }, row.report_date),
  },
  {
    title: '类型',
    key: 'report_type',
    width: 70,
    render: (row: any) => h(NTag, { size: 'small', type: 'info', round: true }, { default: () => row.report_type }),
  },
  { title: '营收', key: 'revenue', width: 130, render: (row: any) => metricCell(row, 'revenue', formatAmount) },
  { title: '净利润', key: 'net_profit', width: 130, render: (row: any) => metricCell(row, 'net_profit', formatAmount) },
  { title: 'ROE', key: 'roe', width: 110, render: (row: any) => metricCell(row, 'roe', (v: number) => v != null ? (v * 100).toFixed(2) + '%' : '-') },
  { title: 'EPS', key: 'eps', width: 110, render: (row: any) => metricCell(row, 'eps', (v: number) => v != null ? '¥' + v.toFixed(2) : '-') },
  { title: 'BPS', key: 'bps', width: 110, render: (row: any) => metricCell(row, 'bps', (v: number) => v != null ? '¥' + v.toFixed(2) : '-') },
  { title: '毛利率', key: 'gross_margin', width: 110, render: (row: any) => metricCell(row, 'gross_margin', (v: number) => v != null ? (v * 100).toFixed(2) + '%' : '-') },
  { title: '净利率', key: 'net_margin', width: 110, render: (row: any) => metricCell(row, 'net_margin', (v: number) => v != null ? (v * 100).toFixed(2) + '%' : '-') },
  { title: '资产负债率', key: 'debt_ratio', width: 110, render: (row: any) => metricCell(row, 'debt_ratio', (v: number) => v != null ? (v * 100).toFixed(2) + '%' : '-') },
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
  // market_cap is in 万元 (10,000 yuan)
  if (cap >= 10000) return '¥' + (cap / 10000).toFixed(2) + '亿'
  return '¥' + cap.toFixed(2) + '万'
}

function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '-'
  return Number(v).toFixed(digits)
}
function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '-'
  return (Number(v) * 100).toFixed(2) + '%'
}

const dividendColumns = [
  { title: '公告日', key: 'announce_date', width: 110 },
  { title: '每股派息(元)', key: 'dividend_per_share', width: 110, render: (r: any) => fmtNum(r.dividend_per_share, 4) },
  { title: '送股', key: 'stock_div_ratio', width: 80, render: (r: any) => fmtNum(r.stock_div_ratio) },
  { title: '转增', key: 'convert_ratio', width: 80, render: (r: any) => fmtNum(r.convert_ratio) },
  { title: '除权日', key: 'ex_date', width: 110 },
]

function calculateAmplitude(quote: DailyQuote): string {
  if (!quote.high || !quote.low || !quote.open) return '-'
  const amplitude = ((quote.high - quote.low) / quote.open) * 100
  return amplitude.toFixed(2) + '%'
}

async function loadData(stockCode: string) {
  stock.value = null
  quotes.value = []
  financials.value = []
  latestIndicators.value = null
  klineLoading.value = true
  finLoading.value = true

  // 2阶段加载：阶段1 立即返回（股票信息 + 实时指标，纯 DB 读），页面头部即时渲染；
  // 阶段2 重数据（K线全量历史 + 财报，首次需 akshare 拉取）异步加载，不阻塞首屏。
  const [stockRes, indicatorsRes] = await Promise.all([
    stocksApi.get(stockCode),
    stocksApi.getIndicators(stockCode),
  ])
  stock.value = stockRes.data
  latestIndicators.value = indicatorsRes.data || null

  // 阶段2：异步，不 await（页面已可交互）
  Promise.all([
    stocksApi.getQuotes(stockCode, { period: klinePeriod.value, limit: 1000 }),
    stocksApi.getFinancials(stockCode),
  ]).then(([quotesRes, finRes]) => {
    quotes.value = quotesRes.data
    financials.value = finRes.data
  }).catch((e) => {
    console.error('Failed to load K-line/financials:', e)
  }).finally(() => {
    klineLoading.value = false
    finLoading.value = false
  })

  // 阶段3：价值投资分析（读缓存+三大报表，最重，最后异步拉，不阻塞）
  stocksApi.getValueAnalysis(stockCode).then((res) => {
    valueAnalysis.value = res.data
  }).catch((e) => console.error('value analysis failed', e))
}

// Real-time refresh: only re-fetch the live indicators + the most recent quote
// (the "实时行情" card) so the page lives up to its name, without refetching
// the whole chart history / financials on every tick.
let realtimeTimer: ReturnType<typeof setInterval> | null = null
const REALTIME_INTERVAL_MS = 10000

async function refreshRealtime(stockCode: string) {
  try {
    // 周K/月K/季K/年K 下不逐 tick 追加（聚合 bar 不随分时变）；只刷新实时指标。
    // 日K 下才取最新 1 根追加到图表末尾。
    const fetches: Promise<any>[] = [stocksApi.getIndicators(stockCode)]
    if (klinePeriod.value === 'daily') {
      fetches.push(stocksApi.getQuotes(stockCode, { period: 'daily', limit: 1 }))
    }
    const [indicatorsRes, quotesRes] = await Promise.all(fetches)
    if (indicatorsRes.data) latestIndicators.value = indicatorsRes.data
    if (klinePeriod.value === 'daily' && quotesRes && quotesRes.data && quotesRes.data.length) {
      const newest = quotesRes.data[quotesRes.data.length - 1]
      const last = quotes.value[quotes.value.length - 1]
      if (!last || new Date(newest.date).getTime() !== new Date(last.date).getTime()) {
        quotes.value = [...quotes.value, newest]
      }
    }
  } catch (e) {
    // Silent — transient network blips shouldn't surface to the user.
    console.debug('realtime refresh failed', e)
  }
}

// 周期切换：重新按新 period 拉取 K线（复用本地缓存，只 resample）
async function onPeriodChange(period: string) {
  try {
    const res = await stocksApi.getQuotes(code.value, { period, limit: 1000 })
    quotes.value = res.data
  } catch (e) {
    console.error('period switch failed', e)
  }
}

function startRealtime(stockCode: string) {
  stopRealtime()
  realtimeTimer = setInterval(() => refreshRealtime(stockCode), REALTIME_INTERVAL_MS)
}

function stopRealtime() {
  if (realtimeTimer) {
    clearInterval(realtimeTimer)
    realtimeTimer = null
  }
}

onMounted(() => {
  loadData(code.value)
  startRealtime(code.value)
})

watch(code, (newCode) => {
  if (newCode) {
    loadData(newCode)
    startRealtime(newCode)
  }
})

onUnmounted(() => {
  stopRealtime()
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

.trend-block {
  background: rgba(30, 41, 59, 0.25);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 12px;
}

.trend-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

/* 价值投资分析 */
.value-section {
  background: rgba(30, 41, 59, 0.25);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 14px 16px;
}
.value-section-title {
  font-size: 12px;
  font-weight: 700;
  color: #6366f1;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border-subtle);
}
.value-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  padding: 3px 0;
}
.value-row span { color: var(--text-tertiary); }
.value-row b { color: var(--text-primary); font-weight: 600; }

.stats-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 20px;
  padding: 10px 14px;
  margin-top: 12px;
  background: rgba(30, 41, 59, 0.2);
  border-radius: 8px;
  font-size: 12px;
}
.stats-label { color: var(--text-tertiary); font-weight: 600; }
.stats-item { color: var(--text-secondary); }
.stats-item b { color: var(--text-primary); margin-right: 4px; }
</style>
