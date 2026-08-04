<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-left">
        <n-icon :size="32" color="#f59e0b">
          <BarChartOutline />
        </n-icon>
        <h2 class="page-title gradient-text">策略回测</h2>
      </div>
    </div>

    <n-card title="创建策略" class="action-card">
      <template #header-extra>
        <n-icon :size="20" color="#00d4aa">
          <CreateOutline />
        </n-icon>
      </template>
      <n-form class="create-form">
        <n-form-item label="策略名称">
          <n-input v-model:value="name" placeholder="例：均线交叉策略" size="large">
            <template #prefix>
              <n-icon :size="18" color="#64748b">
                <PrismOutline />
              </n-icon>
            </template>
          </n-input>
        </n-form-item>
        <n-form-item label="自然语言描述">
          <n-input 
            v-model:value="nlDesc" 
            type="textarea" 
            :rows="5" 
            placeholder="例：均线交叉策略，5日均线上穿20日均线买入，下穿卖出"
            size="large"
          />
        </n-form-item>
        <n-button type="primary" :loading="generating" @click="handleGenerate" size="large" class="action-button">
          <template #icon>
            <n-icon :size="18">
              <SparklesOutline />
            </n-icon>
          </template>
          生成策略
        </n-button>
      </n-form>
    </n-card>

    <!-- 策略分类浏览（idea: 策略分类展示） -->
    <n-card title="策略模板库" class="action-card" v-if="categories">
      <template #header-extra>
        <n-icon :size="20" color="#e94560"><LayersOutline /></n-icon>
      </template>
      <n-collapse>
        <n-collapse-item v-for="(strats, cat) in categories" :key="cat" :title="cat" :name="cat">
          <n-space vertical :size="8">
            <div v-for="s in strats" :key="s.type" class="template-item" @click="useTemplate(s.name)">
              <div class="template-head">
                <b>{{ s.name }}</b>
                <n-space :size="4">
                  <n-tag v-for="t in (s.tags || [])" :key="t" size="tiny" round>{{ t }}</n-tag>
                </n-space>
              </div>
              <p class="template-desc">{{ s.description }}</p>
            </div>
          </n-space>
        </n-collapse-item>
      </n-collapse>
    </n-card>

    <!-- 生成结果：分类+标签+模式 -->
    <n-card v-if="strategyInfo" class="action-card">
      <template #header>
        <span style="font-weight: 600;">策略已生成</span>
      </template>
      <n-space align="center" :size="12">
        <n-tag v-if="strategyInfo.category" type="info" size="small" round>{{ strategyInfo.category }}</n-tag>
        <n-tag v-if="strategyInfo.mode === 'structured'" type="success" size="small" round>结构化匹配</n-tag>
        <n-tag v-else type="warning" size="small" round>LLM 生成</n-tag>
        <n-tag v-for="t in (strategyInfo.tags || [])" :key="t" size="small" round>{{ t }}</n-tag>
        <span v-if="strategyInfo.strategy_type" style="color: var(--text-tertiary); font-size: 13px;">模板: {{ strategyInfo.strategy_type }}</span>
      </n-space>
    </n-card>

    <n-card title="执行回测" class="action-card" v-if="strategyId">
      <template #header-extra>
        <n-icon :size="20" color="#6366f1">
          <PlayOutline />
        </n-icon>
      </template>
      <n-form class="backtest-form">
        <n-grid :cols="2" :x-gap="16">
          <n-gi>
            <n-form-item label="股票代码">
              <n-input v-model:value="stockCodes" placeholder="600519,000001" size="large">
                <template #prefix>
                  <n-icon :size="18" color="#64748b">
                    <CodeOutline />
                  </n-icon>
                </template>
              </n-input>
            </n-form-item>
          </n-gi>
          <n-gi>
            <n-form-item label="初始资金">
              <n-input-number v-model:value="capital" :min="10000" size="large" style="width: 100%;">
                <template #prefix>
                  <n-icon :size="18" color="#64748b">
                    <CashOutline />
                  </n-icon>
                </template>
              </n-input-number>
            </n-form-item>
          </n-gi>
          <n-gi>
            <n-form-item label="开始日期">
              <n-date-picker v-model:value="startDate" type="date" size="large" style="width: 100%;" />
            </n-form-item>
          </n-gi>
          <n-gi>
            <n-form-item label="结束日期">
              <n-date-picker v-model:value="endDate" type="date" size="large" style="width: 100%;" />
            </n-form-item>
          </n-gi>
        </n-grid>
        <n-button type="primary" :loading="running" @click="handleRun" size="large" class="action-button">
          <template #icon>
            <n-icon :size="18">
              <RocketOutline />
            </n-icon>
          </template>
          执行回测
        </n-button>
      </n-form>
    </n-card>

    <n-card title="回测结果" class="result-card" v-if="result">
      <template #header-extra>
        <n-icon :size="20" color="#10b981">
          <TrophyOutline />
        </n-icon>
      </template>
      <n-grid :cols="4" :x-gap="16" class="stats-grid">
        <n-gi>
          <div class="stat-box stat-box-success">
            <div class="stat-label">总收益率</div>
            <div class="stat-value">{{ ((result.total_return ?? 0) * 100).toFixed(2) }}%</div>
          </div>
        </n-gi>
        <n-gi>
          <div class="stat-box stat-box-error">
            <div class="stat-label">最大回撤</div>
            <div class="stat-value">{{ ((result.max_drawdown ?? 0) * 100).toFixed(2) }}%</div>
          </div>
        </n-gi>
        <n-gi>
          <div class="stat-box stat-box-info">
            <div class="stat-label">夏普比率</div>
            <div class="stat-value">{{ result.sharpe_ratio ?? '-' }}</div>
          </div>
        </n-gi>
        <n-gi>
          <div class="stat-box stat-box-warning">
            <div class="stat-label">胜率</div>
            <div class="stat-value">{{ ((result.win_rate ?? 0) * 100).toFixed(2) }}%</div>
          </div>
        </n-gi>
      </n-grid>
      <div class="chart-container" v-if="result.equity_curve">
        <v-chart :option="equityOption" style="height: 400px;" autoresize />
      </div>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useMessage } from 'naive-ui'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import {
  BarChartOutline,
  CreateOutline,
  PrismOutline,
  SparklesOutline,
  PlayOutline,
  CodeOutline,
  CashOutline,
  RocketOutline,
  TrophyOutline,
  LayersOutline
} from '@vicons/ionicons5'
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
const categories = ref<Record<string, any[]> | null>(null)
const strategyInfo = ref<any>(null)

// 加载策略分类
backtestApi.getCategories().then(res => {
  categories.value = res.data.categories
}).catch(() => {})

function useTemplate(name: string) {
  nlDesc.value = name
}

const equityOption = computed(() => ({
  tooltip: { 
    trigger: 'axis',
    backgroundColor: 'rgba(15, 23, 42, 0.95)',
    borderColor: 'rgba(100, 116, 139, 0.3)',
    textStyle: { color: '#e2e8f0' }
  },
  grid: {
    left: '3%',
    right: '4%',
    bottom: '3%',
    containLabel: true
  },
  xAxis: { 
    type: 'category', 
    data: result.value?.equity_curve?.map(e => e.date) || [],
    axisLine: { lineStyle: { color: 'rgba(100, 116, 139, 0.3)' } },
    axisLabel: { color: '#94a3b8' }
  },
  yAxis: { 
    type: 'value',
    axisLine: { lineStyle: { color: 'rgba(100, 116, 139, 0.3)' } },
    axisLabel: { color: '#94a3b8' },
    splitLine: { lineStyle: { color: 'rgba(100, 116, 139, 0.1)' } }
  },
  series: [{ 
    type: 'line', 
    data: result.value?.equity_curve?.map(e => e.value) || [], 
    smooth: true,
    lineStyle: {
      color: {
        type: 'linear',
        x: 0, y: 0, x2: 1, y2: 0,
        colorStops: [
          { offset: 0, color: '#00d4aa' },
          { offset: 1, color: '#6366f1' }
        ]
      },
      width: 3
    },
    areaStyle: {
      color: {
        type: 'linear',
        x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [
          { offset: 0, color: 'rgba(0, 212, 170, 0.3)' },
          { offset: 1, color: 'rgba(99, 102, 241, 0.05)' }
        ]
      }
    }
  }],
}))

function formatDate(ts: number) {
  return new Date(ts).toISOString().split('T')[0]
}

async function handleGenerate() {
  if (!name.value.trim()) {
    message.warning('请输入策略名称')
    return
  }
  if (!nlDesc.value.trim()) {
    message.warning('请输入策略描述')
    return
  }
  generating.value = true
  try {
    const res = await backtestApi.generate(name.value.trim(), nlDesc.value.trim())
    strategyId.value = res.data.id
    strategyInfo.value = res.data
    message.success(res.data.mode === 'structured' ? '策略已生成（结构化匹配）' : '策略代码已生成（LLM）')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '生成失败')
  } finally {
    generating.value = false
  }
}

async function handleRun() {
  if (!strategyId.value) {
    message.warning('请先生成策略代码')
    return
  }
  if (!stockCodes.value.trim()) {
    message.warning('请输入股票代码')
    return
  }
  running.value = true
  try {
    const codes = stockCodes.value.split(',').map(s => s.trim()).filter(s => s)
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
  gap: 12px;
}

.page-title {
  font-size: 28px;
  font-weight: 700;
  margin: 0;
  letter-spacing: -0.5px;
}

.action-card,
.result-card {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 12px !important;
  margin-bottom: 20px;
  transition: all 0.3s;
}

.action-card:hover,
.result-card:hover {
  border-color: var(--border-medium) !important;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
}

.action-card :deep(.n-card-header),
.result-card :deep(.n-card-header) {
  border-bottom: 1px solid var(--border-subtle);
}

.action-card :deep(.n-card-header__main),
.result-card :deep(.n-card-header__main) {
  font-weight: 600;
  font-size: 18px;
  color: var(--text-primary);
}

.create-form :deep(.n-form-item-label),
.backtest-form :deep(.n-form-item-label) {
  font-weight: 600;
  color: var(--text-secondary);
}

.create-form :deep(.n-input),
.backtest-form :deep(.n-input),
.create-form :deep(.n-input-number),
.backtest-form :deep(.n-input-number) {
  background: rgba(30, 41, 59, 0.6) !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 8px !important;
  transition: all 0.3s !important;
}

.create-form :deep(.n-input:hover),
.backtest-form :deep(.n-input:hover),
.create-form :deep(.n-input-number:hover),
.backtest-form :deep(.n-input-number:hover) {
  border-color: var(--primary) !important;
  background: rgba(30, 41, 59, 0.8) !important;
}

.create-form :deep(.n-input--focus),
.backtest-form :deep(.n-input--focus),
.create-form :deep(.n-input-number--focus),
.backtest-form :deep(.n-input-number--focus) {
  border-color: var(--primary) !important;
  box-shadow: 0 0 0 2px rgba(0, 212, 170, 0.15) !important;
  background: rgba(30, 41, 59, 0.9) !important;
}

.create-form :deep(.n-date-picker),
.backtest-form :deep(.n-date-picker) {
  background: rgba(30, 41, 59, 0.6) !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 8px !important;
  transition: all 0.3s !important;
}

.create-form :deep(.n-date-picker:hover),
.backtest-form :deep(.n-date-picker:hover) {
  border-color: var(--primary) !important;
  background: rgba(30, 41, 59, 0.8) !important;
}

.action-button {
  background: linear-gradient(135deg, #00d4aa 0%, #6366f1 100%) !important;
  border: none !important;
  font-weight: 600 !important;
  transition: all 0.3s !important;
  margin-top: 8px;
}

.action-button:hover {
  box-shadow: 0 8px 24px rgba(0, 212, 170, 0.4) !important;
  transform: translateY(-2px);
}

.template-item {
  padding: 10px 14px; border-radius: 10px; cursor: pointer;
  background: var(--bg-surface); border: 1px solid var(--border-subtle);
  transition: border-color 0.2s ease;
}
.template-item:hover { border-color: var(--border-medium); }
.template-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 4px; }
.template-head b { font-size: 14px; color: var(--text-primary); }
.template-desc { font-size: 13px; color: var(--text-tertiary); margin: 0; }

.stats-grid {
  margin-bottom: 24px;
}

.stat-box {
  padding: 20px;
  border-radius: 12px;
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid var(--border-subtle);
  transition: all 0.3s;
  position: relative;
  overflow: hidden;
}

.stat-box::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  opacity: 0.8;
}

.stat-box:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
}

.stat-box-success::before {
  background: linear-gradient(90deg, #10b981, transparent);
}

.stat-box-error::before {
  background: linear-gradient(90deg, #ef4444, transparent);
}

.stat-box-info::before {
  background: linear-gradient(90deg, #6366f1, transparent);
}

.stat-box-warning::before {
  background: linear-gradient(90deg, #f59e0b, transparent);
}

.stat-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  background: linear-gradient(135deg, var(--text-primary), var(--text-secondary));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  line-height: 1;
}

.chart-container {
  padding: 20px;
  background: rgba(30, 41, 59, 0.4);
  border-radius: 12px;
  border: 1px solid var(--border-subtle);
}
</style>
