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
        <n-space>
          <n-button v-if="reviewMode" size="large" @click="exitReview" quaternary>
            ← 返回新辩论
          </n-button>
          <n-button type="primary" :loading="debating"
            :disabled="reviewMode || selectedAgentIds.length < 2"
            @click="handleStart" size="large" block>
            {{ reviewMode ? '回看中（只读）' : debating ? '辩论进行中...' : '开始辩论' }}
          </n-button>
        </n-space>
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
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NTag, useMessage } from 'naive-ui'
import { ChatbubblesOutline, SearchOutline } from '@vicons/ionicons5'
import apiClient from '../api/client'
import { agentsApi, debateApi, stocksApi } from '../api'
import type { Agent, Stock } from '../types'
import MarkdownRenderer from '../components/chat/MarkdownRenderer.vue'

const message = useMessage()
const route = useRoute()
const router = useRouter()
const agents = ref<Agent[]>([])
const agentOptions = ref<{ label: string; value: number }[]>([])
const selectedAgentIds = ref<number[]>([])
const roundCount = ref(3)
const debating = ref(false)
const progressText = ref('')

// Computed-like refs for template
const rounds = ref<any[]>([])
const summary = ref('')
// 回看模式：从 ?session= 加载历史辩论（只读），与"开新辩论"互斥
const reviewMode = ref(false)
const sessionId = ref<number | null>(null)

const ROUND_LABELS: Record<string, string> = {
  analysis: '独立分析', challenge: '质疑', response: '回应', summary: '总结',
}

// 标的搜索（代码/名称/拼音/首字母——复用 /stocks/search 后端能力）
// 模式参考 PortfolioDetail：纯 options（无自定义 render）+ handleSelect 锁定 + 正则抽码
const targetInput = ref('600519')
const stockOptions = ref<any[]>([])
const searching = ref(false)
const selectedStock = ref<Stock | null>(null)
let searchTimeout: ReturnType<typeof setTimeout> | null = null
// 选中标志：naive-ui AutoComplete 选中后会同步触发 update:value(option.label)，
// 用此标志区分"选中自带更新"与"用户键入"，避免选中后立刻清空已选
let selecting = false

const AGENT_COLORS = ['#e94560', '#0f9b8e', '#f5a623', '#5856d6', '#007aff', '#34c759', '#ff9500', '#af52de']

function agentColor(name: string): string {
  let hash = 0
  for (let i = 0; i < name.length; i++) hash = ((hash << 5) - hash + name.charCodeAt(i)) | 0
  return AGENT_COLORS[Math.abs(hash) % AGENT_COLORS.length]
}

// 股票搜索：debounce 300ms，下拉纯文本选项（代码 + 名称）
function handleStockSearch(value: string) {
  if (searchTimeout) clearTimeout(searchTimeout)
  // 选中触发的同步 update（值=label），跳过：保留已选、不重搜、不清空
  if (selecting) {
    selecting = false
    return
  }
  // 用户键入新内容 → 清掉旧选择，重新搜索
  selectedStock.value = null
  if (!value || !value.trim()) {
    stockOptions.value = []
    return
  }
  searchTimeout = setTimeout(async () => {
    searching.value = true
    try {
      const res = await stocksApi.search(value.trim(), 20)
      stockOptions.value = (res.data || []).map((stock: Stock) => ({
        label: `${stock.code} ${stock.name}`,
        value: stock.code,
        stock,
      }))
    } catch (e: any) {
      console.error('Stock search failed:', e.response?.data || e.message)
      stockOptions.value = []
    } finally {
      searching.value = false
    }
  }, 300)
}

// 选中候选 → 锁定该股票；置 selecting 标志，使紧随其后的 update:value(label) 不清空已选
function handleStockSelect(code: string) {
  selecting = true
  const opt = stockOptions.value.find((o) => o.value === code)
  if (opt?.stock) {
    selectedStock.value = opt.stock
  }
}

// 退出回看，回到新辩论表单
function exitReview() {
  reviewMode.value = false
  sessionId.value = null
  rounds.value = []
  summary.value = ''
  router.replace({ query: {} })
}

onMounted(async () => {
  try {
    const res = await agentsApi.list()
    agents.value = res.data
    agentOptions.value = res.data.map((a: Agent) => ({ label: a.name, value: a.id }))
  } catch {}
  // 回看模式：URL 带 ?session= 则加载该 debate 会话的历史
  const sid = route.query.session
  if (sid) {
    await loadDebateReview(Number(sid))
  }
})

// 从持久化的 chat session 重建辩论 rounds/summary（支持刷新/重进回看）
async function loadDebateReview(sid: number) {
  try {
    const res = await apiClient.get(`/chat/sessions/${sid}`)
    const data = res.data
    if (data?.error) {
      message.warning('会话不存在')
      return
    }
    sessionId.value = sid
    reviewMode.value = true
    // 按 meta.round_num 分组 assistant 消息 → rounds；meta.round_type==='summary' → summary
    const byRound = new Map<number, any>()
    for (const m of data.messages || []) {
      const meta = m.meta || {}
      if (m.role === 'assistant' && meta.round_type === 'summary') {
        summary.value = m.content
        continue
      }
      if (m.role === 'assistant' && meta.round_num != null) {
        const r = byRound.get(meta.round_num) || {
          round_type: meta.round_type,
          round_label: ROUND_LABELS[meta.round_type] || meta.round_type,
          round_num: meta.round_num,
          opinions: [],
        }
        r.opinions.push({ agent_name: meta.agent_name || (m.agents_used || [])[0] || 'agent', content: m.content })
        byRound.set(meta.round_num, r)
      }
    }
    rounds.value = [...byRound.values()].sort((a, b) => a.round_num - b.round_num)
    if (data.agent_ids?.length) {
      selectedAgentIds.value = data.agent_ids
    }
  } catch (e: any) {
    message.error('加载辩论历史失败：' + (e.response?.data?.detail || e.message))
  }
}

async function handleStart() {
  if (selectedAgentIds.value.length < 2) return
  // 解析标的代码：优先已选中候选的 code；否则从输入框正则抽 6 位代码
  // （naive-ui AutoComplete 选中后会把 label="code name" 填进输入框，需抽码，参考 PortfolioDetail）
  let code = selectedStock.value?.code || ''
  if (!code) {
    const input = targetInput.value.trim()
    const m = input.match(/^\d{6}/) || input.match(/\d{6}/)
    code = m ? m[0] : ''
  }
  if (!code) {
    message.warning('请先选择分析标的（输入代码/名称/拼音后从下拉选）')
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
          if (eventType === 'session') {
            // 后端建了 debate 会话——记 id 并更新 URL，刷新即可回看
            sessionId.value = data.session_id
            router.replace({ query: { session: String(data.session_id) } })
          } else if (eventType === 'round') {
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
