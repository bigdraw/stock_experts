<template>
  <div class="chat-container">
    <div class="chat-header">
      <h2 class="gradient-text">投资分析对话</h2>
      <n-text depth="3" style="font-size: 13px;">输入问题或分析请求 · / 列技能 · @ 指定 Agent</n-text>
    </div>

    <div class="message-list" ref="msgList">
      <div v-if="!messages.length" class="empty-hint">
        <n-icon :size="48" color="var(--text-tertiary)"><ChatbubbleEllipsesOutline /></n-icon>
        <p>输入你的问题，如"分析 600519 的估值和盈利能力"</p>
        <p style="font-size: 12px; color: var(--text-tertiary);">@巴菲特 @格雷厄姆 分析 600519（指定多个 Agent 对话）</p>
        <p style="font-size: 12px; color: var(--text-tertiary);">/value_analysis 查看可用技能</p>
      </div>
      <div v-for="(msg, i) in messages" :key="i" :class="['message', msg.role]">
        <div v-if="msg.role === 'user'" class="msg-bubble user-bubble">{{ msg.content }}</div>
        <div v-else class="msg-bubble assistant-bubble">
          <div v-if="msg.agents?.length" class="msg-meta">@{{ msg.agents.join(' @') }}</div>
          <div v-if="msg.stocks?.length" class="msg-meta">已检测到股票: {{ msg.stocks.join(', ') }}</div>
          <div class="msg-content">{{ msg.content }}</div>
        </div>
      </div>
      <div v-if="loading" class="message assistant">
        <div class="msg-bubble assistant-bubble"><n-spin size="small" /> 思考中…</div>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="input-area">
      <!-- @提及的 agent 标签 -->
      <div v-if="selectedAgents.length" class="agent-tags">
        <n-tag v-for="a in selectedAgents" :key="a.id" closable size="small" @close="removeAgent(a.id)" type="info" round>
          @{{ a.name }}
        </n-tag>
      </div>

      <n-input-group>
        <n-input
          v-model:value="input"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 4 }"
          placeholder="输入问题…  / 列技能  @ 指定 Agent"
          @keydown.enter.exact.prevent="handleSend"
          @input="handleInput"
        />
        <n-button type="primary" @click="handleSend" :loading="loading" :disabled="!input.trim()">
          发送
        </n-button>
      </n-input-group>

      <!-- /技能 下拉 -->
      <div v-if="showSkills" class="mention-dropdown">
        <div class="dropdown-title">可用技能</div>
        <div v-for="s in skills" :key="s.name" class="dropdown-item" @click="selectSkill(s)">
          <b>{{ s.name }}</b> — <span style="color: var(--text-tertiary); font-size: 12px;">{{ s.desc?.slice(0,60) }}</span>
        </div>
      </div>

      <!-- @agent 下拉 -->
      <div v-if="showAgents" class="mention-dropdown">
        <div class="dropdown-title">选择 Agent</div>
        <div v-for="a in agentList" :key="a.id" class="dropdown-item" @click="selectAgent(a)">
          <b>{{ a.name }}</b> — <span style="color: var(--text-tertiary); font-size: 12px;">{{ a.description?.slice(0,60) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { useMessage } from 'naive-ui'
import { ChatbubbleEllipsesOutline } from '@vicons/ionicons5'
import apiClient from '../api/client'

interface Message {
  role: 'user' | 'assistant'
  content: string
  agents?: string[]
  stocks?: string[]
}
interface Agent { id: number; name: string; description: string }
interface Skill { name: string; desc: string; path: string }

const message = useMessage()
const messages = ref<Message[]>([])
const input = ref('')
const loading = ref(false)
const msgList = ref<HTMLElement | null>(null)

const showSkills = ref(false)
const showAgents = ref(false)
const skills = ref<Skill[]>([])
const agentList = ref<Agent[]>([])
const selectedAgents = ref<Agent[]>([])

onMounted(async () => {
  try {
    const [s, a] = await Promise.all([
      apiClient.get('/chat/skills'),
      apiClient.get('/chat/agents'),
    ])
    skills.value = s.data
    agentList.value = a.data
  } catch (e) {
    console.error('Failed to load skills/agents', e)
  }
})

function handleInput(v: string) {
  // 检测 / 或 @ 触发
  const last = v.slice(-1)
  if (last === '/') { showSkills.value = true; showAgents.value = false }
  else if (last === '@') { showAgents.value = true; showSkills.value = false }
  else { showSkills.value = false; showAgents.value = false }
}

function selectSkill(s: Skill) {
  input.value = input.value.slice(0, -1) + `[技能: ${s.name} — ${s.path}] `
  showSkills.value = false
}

function selectAgent(a: Agent) {
  if (!selectedAgents.value.find(x => x.id === a.id)) {
    selectedAgents.value.push(a)
  }
  input.value = input.value.slice(0, -1) // 去掉 @
  showAgents.value = false
}

function removeAgent(id: number) {
  selectedAgents.value = selectedAgents.value.filter(a => a.id !== id)
}

async function handleSend() {
  if (!input.value.trim()) return
  const userMsg = input.value
  messages.value.push({ role: 'user', content: userMsg })
  input.value = ''
  showSkills.value = false
  showAgents.value = false
  loading.value = true
  await scrollToBottom()

  try {
    const res = await apiClient.post('/chat', {
      message: userMsg,
      agent_ids: selectedAgents.value.map(a => a.id),
    })
    const data = res.data
    messages.value.push({
      role: 'assistant',
      content: data.response || data.error || '（无回复）',
      agents: data.agents_used,
      stocks: data.stocks_detected,
    })
  } catch (e: any) {
    messages.value.push({
      role: 'assistant',
      content: `请求失败: ${e.response?.data?.detail || e.message}`,
    })
  } finally {
    loading.value = false
    await scrollToBottom()
  }
}

async function scrollToBottom() {
  await nextTick()
  if (msgList.value) {
    msgList.value.scrollTop = msgList.value.scrollHeight
  }
}
</script>

<style scoped>
.chat-container {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 140px);
  gap: 16px;
}
.chat-header { text-align: center; }
.chat-header h2 { font-size: 24px; font-weight: 700; margin: 0; }
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  background: rgba(30, 41, 59, 0.2);
  border-radius: 12px;
  border: 1px solid var(--border-subtle);
}
.empty-hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 8px;
  color: var(--text-tertiary);
}
.message { margin-bottom: 12px; }
.message.user { text-align: right; }
.msg-bubble {
  display: inline-block;
  max-width: 80%;
  padding: 10px 16px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
  text-align: left;
  white-space: pre-wrap;
}
.user-bubble {
  background: linear-gradient(135deg, #00d4aa 0%, #6366f1 100%);
  color: white;
}
.assistant-bubble {
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid var(--border-subtle);
  color: var(--text-primary);
}
.msg-meta { font-size: 11px; color: var(--text-tertiary); margin-bottom: 4px; }
.msg-content { white-space: pre-wrap; }
.input-area { position: relative; }
.agent-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.mention-dropdown {
  position: absolute;
  bottom: 100%;
  left: 0;
  right: 0;
  max-height: 240px;
  overflow-y: auto;
  background: var(--bg-elevated);
  border: 1px solid var(--border-medium);
  border-radius: 8px;
  padding: 8px;
  margin-bottom: 4px;
  z-index: 100;
  box-shadow: 0 -4px 16px rgba(0,0,0,0.2);
}
.dropdown-title { font-size: 12px; color: var(--text-tertiary); font-weight: 600; padding: 4px 8px; }
.dropdown-item {
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}
.dropdown-item:hover { background: rgba(0, 212, 170, 0.08); }
</style>
