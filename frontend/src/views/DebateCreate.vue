<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-left">
        <n-icon :size="32" color="#6366f1">
          <ChatbubblesOutline />
        </n-icon>
        <h2 class="page-title gradient-text">辩论分析</h2>
      </div>
    </div>

    <n-card title="发起辩论" class="action-card">
      <template #header-extra>
        <n-icon :size="20" color="#00d4aa">
          <CreateOutline />
        </n-icon>
      </template>
      <n-form class="debate-form">
        <n-form-item label="选择 Agent（至少2个）">
          <n-select 
            v-model:value="selectedAgents" 
            :options="agentOptions" 
            multiple 
            :min="2"
            size="large"
            placeholder="选择参与辩论的 Agent"
          />
        </n-form-item>
        <n-grid :cols="2" :x-gap="16">
          <n-gi>
            <n-form-item label="分析标的">
              <n-input v-model:value="targetCode" placeholder="股票代码，如 600519" size="large">
                <template #prefix>
                  <n-icon :size="18" color="#64748b">
                    <CodeOutline />
                  </n-icon>
                </template>
              </n-input>
            </n-form-item>
          </n-gi>
          <n-gi>
            <n-form-item label="辩论轮数">
              <n-input-number v-model:value="rounds" :min="1" :max="5" size="large" style="width: 100%;" />
            </n-form-item>
          </n-gi>
        </n-grid>
        <n-button 
          type="primary" 
          :loading="debating" 
          @click="handleStart" 
          :disabled="selectedAgents.length < 2"
          size="large"
          class="action-button"
        >
          <template #icon>
            <n-icon :size="18">
              <FlashOutline />
            </n-icon>
          </template>
          开始辩论
        </n-button>
      </n-form>
    </n-card>

    <n-card title="辩论过程" class="result-card" v-if="debateResult">
      <template #header-extra>
        <n-icon :size="20" color="#f59e0b">
          <ListOutline />
        </n-icon>
      </template>
      <n-collapse class="debate-collapse">
        <n-collapse-item 
          v-for="(round, i) in debateResult.rounds" 
          :key="i" 
          :title="`第 ${i+1} 轮 - ${round.round_type}`"
        >
          <div v-for="op in round.opinions" :key="op.agent_name" class="opinion-item">
            <n-tag type="info" round size="large">
              <template #icon>
                <n-icon :size="14">
                  <PersonOutline />
                </n-icon>
              </template>
              {{ op.agent_name }}
            </n-tag>
            <p class="opinion-content">{{ op.content }}</p>
          </div>
        </n-collapse-item>
      </n-collapse>
    </n-card>

    <n-card title="总结报告" class="summary-card" v-if="debateResult?.summary">
      <template #header-extra>
        <n-icon :size="20" color="#10b981">
          <DocumentTextOutline />
        </n-icon>
      </template>
      <div class="summary-content">{{ debateResult.summary }}</div>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useMessage } from 'naive-ui'
import { 
  ChatbubblesOutline, 
  CreateOutline, 
  CodeOutline,
  FlashOutline,
  ListOutline,
  PersonOutline,
  DocumentTextOutline
} from '@vicons/ionicons5'
import { agentsApi, debateApi } from '../api'
import type { Agent, DebateResult } from '../types'

const message = useMessage()
const agents = ref<Agent[]>([])
const agentOptions = ref<any[]>([])
const selectedAgents = ref<number[]>([])
const targetCode = ref('600519')
const rounds = ref(3)
const debating = ref(false)
const debateResult = ref<DebateResult | null>(null)

onMounted(async () => {
  const res = await agentsApi.list()
  agents.value = res.data
  agentOptions.value = res.data.map((a: Agent) => ({ label: `${a.name} (${a.type})`, value: a.id }))
})

async function handleStart() {
  if (selectedAgents.value.length < 2) {
    message.warning('请至少选择2个Agent')
    return
  }
  if (!targetCode.value.trim()) {
    message.warning('请输入目标股票代码')
    return
  }
  debating.value = true
  debateResult.value = null
  try {
    const res = await debateApi.start(selectedAgents.value, 'stock', targetCode.value.trim(), rounds.value)
    debateResult.value = res.data
    message.success('辩论完成')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '辩论失败')
  } finally {
    debating.value = false
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
.result-card,
.summary-card {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 12px !important;
  margin-bottom: 20px;
  transition: all 0.3s;
}

.action-card:hover,
.result-card:hover,
.summary-card:hover {
  border-color: var(--border-medium) !important;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
}

.action-card :deep(.n-card-header),
.result-card :deep(.n-card-header),
.summary-card :deep(.n-card-header) {
  border-bottom: 1px solid var(--border-subtle);
}

.action-card :deep(.n-card-header__main),
.result-card :deep(.n-card-header__main),
.summary-card :deep(.n-card-header__main) {
  font-weight: 600;
  font-size: 18px;
  color: var(--text-primary);
}

.debate-form :deep(.n-form-item-label) {
  font-weight: 600;
  color: var(--text-secondary);
}

.debate-form :deep(.n-input),
.debate-form :deep(.n-input-number),
.debate-form :deep(.n-select) {
  background: rgba(30, 41, 59, 0.6) !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 8px !important;
  transition: all 0.3s !important;
}

.debate-form :deep(.n-input:hover),
.debate-form :deep(.n-input-number:hover),
.debate-form :deep(.n-select:hover) {
  border-color: var(--primary) !important;
  background: rgba(30, 41, 59, 0.8) !important;
}

.debate-form :deep(.n-input--focus),
.debate-form :deep(.n-input-number--focus),
.debate-form :deep(.n-select--focus) {
  border-color: var(--primary) !important;
  box-shadow: 0 0 0 2px rgba(0, 212, 170, 0.15) !important;
  background: rgba(30, 41, 59, 0.9) !important;
}

.action-button {
  background: linear-gradient(135deg, #00d4aa 0%, #6366f1 100%) !important;
  border: none !important;
  font-weight: 600 !important;
  transition: all 0.3s !important;
  margin-top: 8px;
}

.action-button:hover:not(:disabled) {
  box-shadow: 0 8px 24px rgba(0, 212, 170, 0.4) !important;
  transform: translateY(-2px);
}

.action-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.debate-collapse :deep(.n-collapse-item__header) {
  background: rgba(30, 41, 59, 0.6);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 8px;
  font-weight: 600;
  color: var(--text-primary);
}

.debate-collapse :deep(.n-collapse-item__content-inner) {
  padding: 16px;
}

.opinion-item {
  margin-bottom: 20px;
  padding: 16px;
  background: rgba(30, 41, 59, 0.4);
  border-radius: 8px;
  border-left: 3px solid var(--primary);
}

.opinion-content {
  margin-top: 12px;
  white-space: pre-wrap;
  line-height: 1.8;
  color: var(--text-secondary);
  font-size: 14px;
}

.summary-content {
  white-space: pre-wrap;
  line-height: 1.8;
  color: var(--text-secondary);
  font-size: 14px;
  padding: 16px;
  background: rgba(30, 41, 59, 0.4);
  border-radius: 8px;
  border-left: 3px solid #10b981;
}
</style>
