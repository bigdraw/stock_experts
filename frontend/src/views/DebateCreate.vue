<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-left">
        <n-icon :size="28" color="var(--primary)"><ChatbubblesOutline /></n-icon>
        <h2 class="page-title">多 Agent 辩论</h2>
      </div>
    </div>

    <!-- 配置 -->
    <n-card class="action-card">
      <n-form>
        <n-form-item label="选择 Agent（至少 2 个）">
          <n-select v-model:value="selectedAgentIds" multiple filterable
            :options="agentOptions" placeholder="选择参与辩论的投资大师" size="large" />
        </n-form-item>
        <n-grid :cols="2" :x-gap="16">
          <n-gi>
            <n-form-item label="分析标的">
              <n-auto-complete
                v-model:value="targetInput"
                :options="stockOptions"
                :loading="searching"
                placeholder="输入代码、名称、拼音或首字母（如 600519 / 茅台 / mtfy）"
                clearable
                size="large"
                @update:value="handleStockSearch"
                @select="handleStockSelect"
              >
                <template #prefix>
                  <n-icon :size="18" color="#64748b"><SearchOutline /></n-icon>
                </template>
              </n-auto-complete>
              <div v-if="selectedStock" class="selected-stock">
                已选：<n-tag size="small" type="info" round>{{ selectedStock.code }}</n-tag>
                <span class="selected-name">{{ selectedStock.name }}</span>
                <n-tag size="tiny" :type="selectedStock.market === 'SH' ? 'success' : 'warning'" round>{{ selectedStock.market }}</n-tag>
              </div>
            </n-form-item>
          </n-gi>
          <n-gi>
            <n-form-item label="辩论轮数">
              <n-input-number v-model:value="roundCount" :min="1" :max="5" size="large" style="width:100%" />
            </n-form-item>
          </n-gi>
        </n-grid>
        <n-button type="primary" :loading="debating" :disabled="selectedAgentIds.length < 2"
          @click="handleStart" size="large" block>
          {{ debating ? '辩论进行中...' : '开始辩论' }}
        </n-button>
      </n-form>
    </n-card>

    <!-- 数据能力提示 -->
    <n-card class="action-card" size="small">
      <n-space align="center" :size="12">
        <n-tag type="info" size="small" round>FactBook 共享事实基础</n-tag>
        <span style="font-size:13px; color:var(--text-tertiary)">辩论前自动采集：6维价值分析(trend20期+分红) + 5年K线趋势 + 行业动态 + 宏观政策 + 沪深300市场状态，所有 agent 基于同一事实论证</span>
      </n-space>
    </n-card>

    <!-- 进度提示 -->
    <div v-if="debating" class="progress-hint">
      <n-spin size="small" />
      <span>{{ progressText }}</span>
    </div>

    <!-- 辩论过程：逐轮展开显示 -->
    <div v-if="rounds.length" class="debate-rounds">
      <div v-for="(round, i) in rounds" :key="i" class="round-section">
        <div class="round-header">
          <span class="round-num">第 {{ i + 1 }} 轮</span>
          <n-tag size="small" round>{{ round.round_label || round.round_type }}</n-tag>
        </div>
        <div v-for="op in round.opinions" :key="op.agent_name" class="opinion-card">
          <div class="opinion-agent" :style="{ borderLeftColor: agentColor(op.agent_name) }">
            <span class="agent-name">{{ op.agent_name }}</span>
          </div>
          <div class="opinion-body">
            <MarkdownRenderer v-if="op.content" :content="op.content" />
          </div>
        </div>
      </div>
    </div>

    <!-- 总结报告 -->
    <n-card v-if="summary" class="summary-card">
      <template #header>
        <span style="font-weight:600;">总结报告</span>
      </template>
      <MarkdownRenderer :content="summary" />
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, h, onMounted } from 'vue'
import { NTag, useMessage } from 'naive-ui'
import { ChatbubblesOutline, SearchOutline } from '@vicons/ionicons5'
import { agentsApi, debateApi, stocksApi } from '../api'
import type { Agent, Stock } from '../types'
import MarkdownRenderer from '../components/chat/MarkdownRenderer.vue'

const message = useMessage()
const agents = ref<Agent[]>([])
const agentOptions = ref<{ label: string; value: number }[]>([])
const selectedAgentIds = ref<number[]>([])
const roundCount = ref(3)
const debating = ref(false)
const progressText = ref('')

// Computed-like refs for template
const rounds = ref<any[]>([])
const summary = ref('')

// 标的搜索（代码/名称/拼音/首字母——复用 /stocks/search 后端能力）
const targetInput = ref('600519')
const stockOptions = ref<any[]>([])
const searching = ref(false)
const selectedStock = ref<Stock | null>(null)
let searchTimeout: ReturnType<typeof setTimeout> | null = null

const AGENT_COLORS = ['#e94560', '#0f9b8e', '#f5a623', '#5856d6', '#007aff', '#34c759', '#ff9500', '#af52de']

function agentColor(name: string): string {
  let hash = 0
  for (let i = 0; i < name.length; i++) hash = ((hash << 5) - hash + name.charCodeAt(i)) | 0
  return AGENT_COLORS[Math.abs(hash) % AGENT_COLORS.length]
}

// 股票搜索：debounce 300ms，下拉展示 代码+名称+市场
function handleStockSearch(value: string) {
  if (searchTimeout) clearTimeout(searchTimeout)
  // 选中后 naive-ui AutoComplete 会用 option.label 同步触发一次 update:value；
  // 当该值等于已选 code 时属"选中自带更新"，保留已选、不重搜（避免清空选择）
  if (selectedStock.value && value === selectedStock.value.code) return
  if (!value || !value.trim()) {
    stockOptions.value = []
    return
  }
  // 用户键入新内容（与已选 code 不同）→ 清掉旧选择，重新搜索
  selectedStock.value = null
  searchTimeout = setTimeout(async () => {
    searching.value = true
    try {
      const res = await stocksApi.search(value.trim(), 20)
      stockOptions.value = (res.data || []).map((stock: Stock) => ({
        // label 用于"选中后填入输入框的值"——设为 code，确保输入框得到正确代码
        // （naive-ui AutoComplete 默认 clearAfterSelect=false 会把 label 填进输入框）
        label: stock.code,
        value: stock.code,
        stock,
        // dropdown 展示走自定义 render（代码+名称+市场），不受 label 影响
        render: () => h('div', { class: 'stock-option-item' }, [
          h(NTag, { size: 'small', type: 'info', round: true }, { default: () => stock.code }),
          h('span', { class: 'stock-option-name' }, stock.name),
          h(NTag, {
            size: 'tiny',
            type: stock.market === 'SH' ? 'success' : 'warning',
            round: true,
          }, { default: () => stock.market }),
        ]),
      }))
    } catch (e: any) {
      console.error('Stock search failed:', e.response?.data || e.message)
      stockOptions.value = []
    } finally {
      searching.value = false
    }
  }, 300)
}

// 选中候选 → 锁定该股票 code 作为辩论 target
function handleStockSelect(code: string) {
  const opt = stockOptions.value.find((o) => o.value === code)
  if (opt?.stock) {
    selectedStock.value = opt.stock
    targetInput.value = opt.stock.code
  }
}

onMounted(async () => {
  try {
    const res = await agentsApi.list()
    agents.value = res.data
    agentOptions.value = res.data.map((a: Agent) => ({ label: a.name, value: a.id }))
  } catch {}
})

async function handleStart() {
  if (selectedAgentIds.value.length < 2) return
  // 优先用"已选中候选"的 code；未选中时回退到输入框原文（可能是手输的合法 code）
  const code = selectedStock.value?.code || targetInput.value.trim()
  if (!code) {
    message.warning('请先选择分析标的')
    return
  }

  debating.value = true
  rounds.value = []
  summary.value = ''
  progressText.value = '正在准备 FactBook 数据（价值分析/K线/行业/宏观/市场状态）...'

  try {
    const res = await debateApi.startStream(
      selectedAgentIds.value, 'stock', code, roundCount.value
    )
    if (!res.ok) throw new Error(`HTTP ${res.status}`)

    const reader = res.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let idx
      while ((idx = buffer.indexOf('\n\n')) >= 0) {
        const block = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 2)
        const lines = block.split('\n')
        const eventType = lines[0]?.replace('event: ', '') || ''
        const dataStr = lines[1]?.replace('data: ', '') || '{}'
        try {
          const data = JSON.parse(dataStr)
          if (eventType === 'round') {
            rounds.value.push(data)
            progressText.value = `第 ${rounds.value.length} 轮完成，正在下一轮...`
          } else if (eventType === 'summary') {
            summary.value = data.summary || ''
            progressText.value = '辩论完成'
          } else if (eventType === 'done') {
            progressText.value = '辩论完成'
          } else if (eventType === 'error') {
            message.error(data.message || '辩论出错')
          }
        } catch {}
      }
    }
    message.success('辩论完成')
  } catch (e: any) {
    message.error(e.message || '辩论失败')
  } finally {
    debating.value = false
    progressText.value = ''
  }
}
</script>

<style scoped>
.page-container { animation: fadeIn 0.3s ease; padding: 24px; max-width: 960px; margin: 0 auto; }
.page-header { margin-bottom: 24px; }
.header-left { display: flex; align-items: center; gap: 12px; }
.page-title { font-size: 22px; font-weight: 700; margin: 0; }

.action-card {
  background: var(--bg-elevated) !important; border: 1px solid var(--border-subtle) !important;
  border-radius: var(--radius-lg) !important; margin-bottom: 16px;
}

.progress-hint {
  display: flex; align-items: center; gap: 10px; padding: 16px; font-size: 14px;
  color: var(--text-tertiary);
}

.debate-rounds { margin-bottom: 24px; }
.round-section { margin-bottom: 24px; }
.round-header {
  display: flex; align-items: center; gap: 10px; margin-bottom: 12px;
  padding-bottom: 8px; border-bottom: 1px solid var(--border-subtle);
}
.round-num { font-size: 15px; font-weight: 600; color: var(--text-primary); }

.opinion-card {
  display: flex; gap: 0; margin-bottom: 12px;
  background: var(--bg-elevated); border-radius: var(--radius-sm);
  border: 1px solid var(--border-subtle); overflow: hidden;
}
.opinion-agent {
  flex-shrink: 0; padding: 12px 14px; min-width: 100px; border-left: 3px solid var(--primary);
  background: var(--bg-surface); display: flex; align-items: flex-start;
}
.agent-name { font-size: 13px; font-weight: 600; color: var(--text-secondary); }
.opinion-body { flex: 1; padding: 12px 16px; min-width: 0; }

.summary-card {
  background: var(--bg-elevated) !important; border: 1px solid var(--border-medium) !important;
  border-radius: var(--radius-lg) !important;
}

/* 标的搜索下拉项 */
:deep(.stock-option-item) {
  display: flex; align-items: center; gap: 8px; padding: 6px 8px;
}
:deep(.stock-option-name) {
  font-weight: 600; color: var(--text-primary); flex: 1; min-width: 0;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.selected-stock {
  display: flex; align-items: center; gap: 6px; margin-top: 6px;
  font-size: 13px; color: var(--text-secondary);
}
.selected-name { font-weight: 600; color: var(--text-primary); }
</style>
