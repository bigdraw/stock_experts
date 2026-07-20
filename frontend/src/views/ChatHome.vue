<template>
  <div class="chat-home-container">
    <!-- 左侧会话列表 -->
    <div class="sidebar-area">
      <SessionSidebar />
    </div>

    <!-- 右侧聊天主区 -->
    <div class="chat-main">
      <!-- 消息列表 -->
      <div class="message-list" ref="msgList">
        <div v-if="!chatStore.messages.length" class="empty-hint">
          <n-icon :size="48" color="var(--text-tertiary)"><ChatbubbleEllipsesOutline /></n-icon>
          <p>输入问题，如"分析 600519 的估值和盈利能力"</p>
          <p style="font-size: 12px; color: var(--text-tertiary);">@巴菲特 @格雷厄姆 分析 600519</p>
          <n-space :size="12" style="margin-top: 20px;" justify="center">
            <n-button size="small" secondary @click="quickFill('分析个股 600519 的估值和盈利能力')">个股分析</n-button>
            <n-button size="small" secondary @click="$router.push('/portfolios')">组合管理</n-button>
            <n-button size="small" secondary @click="$router.push('/backtest')">策略回测</n-button>
            <n-button size="small" secondary @click="$router.push('/debate')">辩论分析</n-button>
            <n-button size="small" secondary @click="$router.push('/filters')">筛选工具</n-button>
          </n-space>
        </div>

        <div v-for="(msg, i) in chatStore.messages" :key="i" :class="['message', msg.role]">
          <div v-if="msg.role === 'user'" class="msg-bubble user-bubble">{{ msg.content }}</div>
          <div v-else class="msg-bubble assistant-bubble">
            <div v-if="msg.agents_used?.length" class="msg-meta">@{{ msg.agents_used.join(' @') }}</div>
            <div v-if="msg.stocks_detected?.length" class="msg-meta">已检测到股票: {{ msg.stocks_detected.join(', ') }}</div>
            <MarkdownRenderer v-if="msg.content" :content="msg.content" />
            <span v-if="msg.streaming" class="cursor">▋</span>
          </div>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="input-area">
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
            placeholder="输入问题…  @ 指定 Agent"
            @keydown.enter.exact.prevent="handleSend"
          />
          <n-button v-if="!chatStore.streaming" type="primary" @click="handleSend" :disabled="!input.trim()">发送</n-button>
          <n-button v-else type="error" @click="chatStore.stopStreaming()">停止</n-button>
        </n-input-group>
        <div class="quick-actions-bar">
          <n-button size="tiny" quaternary @click="quickFill('分析个股 600519 的估值和盈利能力')">个股分析</n-button>
          <n-button size="tiny" quaternary @click="$router.push('/portfolios')">组合管理</n-button>
          <n-button size="tiny" quaternary @click="quickFill('分析我的投资组合风险')">组合分析</n-button>
          <n-button size="tiny" quaternary @click="$router.push('/backtest')">策略回测</n-button>
          <n-button size="tiny" quaternary @click="$router.push('/debate')">辩论分析</n-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import { NIcon, NSpace, NTag, NInputGroup, NInput, NButton } from 'naive-ui'
import { ChatbubbleEllipsesOutline } from '@vicons/ionicons5'
import { useChatStore } from '../stores/chat'
import SessionSidebar from '../components/chat/SessionSidebar.vue'
import MarkdownRenderer from '../components/chat/MarkdownRenderer.vue'
import apiClient from '../api/client'

const chatStore = useChatStore()
const route = useRoute()
const input = ref('')
const msgList = ref<HTMLElement | null>(null)
const agentList = ref<any[]>([])
const selectedAgents = ref<any[]>([])

onMounted(async () => {
  await chatStore.loadSessions()
  // 路由指定会话
  const sid = route.params.sessionId
  if (sid) {
    await chatStore.selectSession(parseInt(sid as string))
  } else if (chatStore.currentSessionId) {
    await chatStore.selectSession(chatStore.currentSessionId)
  }
  // 加载 agent 列表
  try {
    const res = await apiClient.get('/chat/agents')
    agentList.value = res.data
  } catch { /* ignore */ }
})

// @agent 提及
function handleInput(v: string) {
  const last = v.slice(-1)
  if (last === '@') {
    // 简单实现：显示第一个未选 agent
    const next = agentList.value.find(a => !selectedAgents.value.find(s => s.id === a.id))
    if (next) {
      selectedAgents.value.push(next)
      input.value = input.value.slice(0, -1)
    }
  }
}

function removeAgent(id: number) {
  selectedAgents.value = selectedAgents.value.filter(a => a.id !== id)
}

function quickFill(text: string) {
  input.value = text
}

async function handleSend() {
  if (!input.value.trim()) return
  const text = input.value
  input.value = ''
  await chatStore.sendMessage(text, selectedAgents.value.map(a => a.id))
  await scrollToBottom()
}

watch(() => chatStore.messages.length, async () => {
  await scrollToBottom()
})
watch(() => chatStore.messages.at(-1)?.content, async () => {
  await scrollToBottom()
})

async function scrollToBottom() {
  await nextTick()
  if (msgList.value) msgList.value.scrollTop = msgList.value.scrollHeight
}
</script>

<style scoped>
.chat-home-container { display: flex; height: calc(100vh - 110px); gap: 0; }
.sidebar-area { width: 260px; flex-shrink: 0; border-right: 1px solid var(--border-subtle); }
.chat-main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.message-list { flex: 1; overflow-y: auto; padding: 16px 24px; }
.empty-hint { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; gap: 8px; color: var(--text-tertiary); text-align: center; }
.message { margin-bottom: 16px; }
.message.user { text-align: right; }
.msg-bubble { display: inline-block; max-width: 85%; padding: 12px 18px; border-radius: 14px; font-size: 14px; line-height: 1.6; text-align: left; }
.user-bubble { background: linear-gradient(135deg, #00d4aa 0%, #6366f1 100%); color: white; }
.assistant-bubble { background: rgba(30,41,59,0.6); border: 1px solid var(--border-subtle); color: var(--text-primary); }
.msg-meta { font-size: 11px; color: var(--text-tertiary); margin-bottom: 6px; }
.cursor { animation: blink 1s infinite; color: #6366f1; }
@keyframes blink { 0%,50% {opacity:1} 51%,100% {opacity:0} }
.input-area { border-top: 1px solid var(--border-subtle); padding: 12px 24px; }
.agent-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.quick-actions-bar { display: flex; gap: 4px; margin-top: 8px; flex-wrap: wrap; }
</style>
