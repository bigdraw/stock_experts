<template>
  <n-space vertical>
    <n-card title="发起辩论">
      <n-form>
        <n-form-item label="选择 Agent（至少2个）">
          <n-select v-model:value="selectedAgents" :options="agentOptions" multiple :min="2" />
        </n-form-item>
        <n-form-item label="分析标的">
          <n-input v-model:value="targetCode" placeholder="股票代码，如 600519" />
        </n-form-item>
        <n-form-item label="辩论轮数">
          <n-input-number v-model:value="rounds" :min="1" :max="5" />
        </n-form-item>
        <n-button type="primary" :loading="debating" @click="handleStart" :disabled="selectedAgents.length < 2">
          开始辩论
        </n-button>
      </n-form>
    </n-card>

    <n-card title="辩论过程" v-if="debateResult">
      <n-collapse>
        <n-collapse-item v-for="(round, i) in debateResult.rounds" :key="i" :title="`第 ${i+1} 轮 - ${round.round_type}`">
          <div v-for="op in round.opinions" :key="op.agent_name" style="margin-bottom: 16px">
            <n-tag type="info">{{ op.agent_name }}</n-tag>
            <p style="white-space: pre-wrap; margin-top: 8px">{{ op.content }}</p>
          </div>
        </n-collapse-item>
      </n-collapse>
    </n-card>

    <n-card title="总结报告" v-if="debateResult?.summary">
      <div style="white-space: pre-wrap">{{ debateResult.summary }}</div>
    </n-card>
  </n-space>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useMessage } from 'naive-ui'
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
  debating.value = true
  debateResult.value = null
  try {
    const res = await debateApi.start(selectedAgents.value, 'stock', targetCode.value, rounds.value)
    debateResult.value = res.data
    message.success('辩论完成')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '辩论失败')
  } finally {
    debating.value = false
  }
}
</script>
