<template>
  <div class="chat-home">
    <SessionSidebar />
    <div class="chat-main">
      <div class="message-list" ref="msgList">
        <div v-if="!chatStore.messages.length" class="empty-state">
          <div class="empty-icon">💬</div>
          <p class="empty-title">开始对话</p>
          <p class="empty-hint">输入问题，或试试：</p>
          <div class="chips">
            <button v-for="s in suggestions" :key="s" class="chip" @click="quickFill(s)">{{ s }}</button>
          </div>
          <div class="quick-nav">
            <n-button size="small" secondary @click="$router.push('/stocks')">📈 股票</n-button>
            <n-button size="small" secondary @click="$router.push('/portfolios')">💼 组合</n-button>
            <n-button size="small" secondary @click="$router.push('/backtest')">📊 回测</n-button>
          </div>
        </div>
        <div v-for="(msg, i) in chatStore.messages" :key="i" :class="['msg-row', msg.role]">
          <div v-if="msg.role === 'user'" class="bubble user-bubble">{{ msg.content }}</div>
          <div v-else class="bubble assistant-bubble">
            <div v-if="msg.agents_used?.length" class="msg-agents">{{ msg.agents_used.map(a => '@'+a).join(' ') }}</div>
            <MarkdownRenderer v-if="msg.content" :content="msg.content" />
            <span v-if="msg.streaming" class="typing-cursor">▋</span>
          </div>
        </div>
      </div>
      <div class="input-bar">
        <div v-if="selectedAgents.length" class="agent-tags">
          <n-tag v-for="a in selectedAgents" :key="a.id" closable size="small" @close="removeAgent(a.id)" type="info">{{ '@'+a.name }}</n-tag>
        </div>
        <div class="input-row">
          <n-input v-model:value="input" type="textarea" :autosize="{ minRows:1, maxRows:5 }" placeholder="输入消息…  @ 指定 Agent" @keydown.enter.exact.prevent="handleSend" :bordered="false" class="chat-input" />
          <n-button v-if="!chatStore.streaming" type="primary" @click="handleSend" :disabled="!input.trim()">发送</n-button>
          <n-button v-else type="error" @click="chatStore.stopStreaming()">停止</n-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import { NButton, NTag, NInput } from 'naive-ui'
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
const suggestions = ['分析 600519 的估值和盈利能力', '@巴菲特 茅台值不值得买', '分析我的投资组合风险']

onMounted(async () => {
  await chatStore.loadSessions()
  const sid = route.params.sessionId
  if (sid) await chatStore.selectSession(parseInt(sid as string))
  else if (chatStore.currentSessionId) await chatStore.selectSession(chatStore.currentSessionId)
  try { agentList.value = (await apiClient.get('/chat/agents')).data } catch {}
})

function removeAgent(id: number) { selectedAgents.value = selectedAgents.value.filter(a => a.id !== id) }
function quickFill(text: string) { input.value = text }
async function handleSend() {
  if (!input.value.trim()) return
  const text = input.value; input.value = ''
  await chatStore.sendMessage(text, selectedAgents.value.map(a => a.id))
  await scrollToBottom()
}
watch(() => chatStore.messages.length, () => scrollToBottom())
watch(() => chatStore.messages.at(-1)?.content, () => scrollToBottom())
async function scrollToBottom() {
  await nextTick()
  if (msgList.value) msgList.value.scrollTop = msgList.value.scrollHeight
}
</script>

<style scoped>
.chat-home { display: flex; height: calc(100vh - 1px); background: var(--bg-base); }
.chat-main { flex: 1; display: flex; flex-direction: column; min-width: 0; }

.message-list { flex: 1; overflow-y: auto; padding: 24px 0; }
.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; gap: 8px; }
.empty-icon { font-size: 40px; margin-bottom: 4px; }
.empty-title { font-size: 20px; font-weight: 600; color: var(--text-primary); }
.empty-hint { font-size: 14px; color: var(--text-tertiary); }
.chips { display: flex; flex-wrap: wrap; gap: 8px; max-width: 500px; justify-content: center; margin: 12px 0; }
.chip {
  padding: 8px 14px; border-radius: var(--radius-sm); background: var(--bg-elevated);
  border: 1px solid var(--border-medium); color: var(--text-secondary); font-size: 13px;
  cursor: pointer; transition: opacity var(--transition);
}
.chip:hover { opacity: 0.85; border-color: var(--primary); color: var(--primary); }
.quick-nav { display: flex; gap: 8px; margin-top: 16px; }

.msg-row { padding: 4px 24px; }
.msg-row.user { display: flex; justify-content: flex-end; }
.bubble {
  max-width: 75%; padding: 12px 16px; font-size: 15px; line-height: 1.6; word-wrap: break-word;
}
.user-bubble {
  background: var(--primary); color: #fff;
  border-radius: var(--radius-lg) var(--radius-lg) 4px var(--radius-lg);
}
.assistant-bubble {
  background: var(--bg-elevated); color: var(--text-primary);
  border-radius: var(--radius-lg) var(--radius-lg) var(--radius-lg) 4px;
}
.msg-agents { font-size: 12px; color: var(--text-tertiary); margin-bottom: 6px; }
.typing-cursor { color: var(--primary); animation: blink 1s infinite; }
@keyframes blink { 0%,50%{opacity:1} 51%,100%{opacity:0} }

.input-bar { border-top: 1px solid var(--border-subtle); padding: 12px 24px 20px; }
.agent-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
.input-row { display: flex; align-items: flex-end; gap: 8px; }
.chat-input {
  background: var(--bg-surface) !important; border-radius: var(--radius-sm) !important; padding: 10px 16px !important;
  border: 1px solid var(--border-medium) !important;
}
.chat-input :deep(.n-input__textarea-el) { color: var(--text-primary) !important; }
</style>
