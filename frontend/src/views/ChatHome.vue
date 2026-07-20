<template>
  <div class="chat-shell">
    <!-- 侧边栏 -->
    <SessionSidebar />

    <!-- 主区：纵向 flex，消息区 flex:1 滚动，输入栏同级沉底 -->
    <div class="chat-main">
      <!-- 消息区：flex:1 + overflow:auto，输入栏永远在视口底部 -->
      <div class="msg-scroll" ref="msgList">
        <div class="msg-inner">
          <!-- 空状态 -->
          <div v-if="!chatStore.messages.length" class="welcome">
            <div class="welcome-spacer" />
            <div class="welcome-content">
              <div class="welcome-icon">📈</div>
              <h2 class="welcome-title">AI 投资分析</h2>
              <p class="welcome-desc">@巴菲特 分析 600519 — 大师替你思考，工具替你取数</p>
              <div class="suggestions">
                <button v-for="s in suggestions" :key="s" class="suggestion" @click="quickFill(s)">{{ s }}</button>
              </div>
              <div class="quick-nav">
                <n-button size="small" secondary @click="$router.push('/stocks')">股票</n-button>
                <n-button size="small" secondary @click="$router.push('/portfolios')">组合</n-button>
                <n-button size="small" secondary @click="$router.push('/backtest')">回测</n-button>
                <n-button size="small" secondary @click="$router.push('/debate')">辩论</n-button>
              </div>
            </div>
          </div>

          <!-- 消息列表 -->
          <template v-for="(msg, i) in chatStore.messages" :key="i">
            <div v-if="msg.role === 'user'" class="msg-row user">
              <div class="bubble user-bubble">{{ msg.content }}</div>
            </div>
            <div v-else class="msg-row assistant">
              <div v-if="msg.agents_used?.length" class="msg-agents">{{ msg.agents_used.map(a => '@'+a).join(' ') }}</div>
              <div class="assistant-content">
                <MarkdownRenderer v-if="msg.content" :content="msg.content" />
                <span v-if="msg.streaming" class="cursor">▋</span>
              </div>
            </div>
          </template>
        </div>
      </div>

      <!-- 输入栏：flex 同级，不 absolute，不随消息滚 -->
      <div class="input-area">
        <div class="input-container">
          <div v-if="selectedAgents.length" class="agent-tags">
            <n-tag v-for="a in selectedAgents" :key="a.id" closable size="small" @close="removeAgent(a.id)" type="info">{{ '@'+a.name }}</n-tag>
          </div>
          <div class="input-row">
            <n-input
              v-model:value="input"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 5 }"
              placeholder="输入消息…  @ 指定 Agent"
              @keydown.enter.exact.prevent="handleSend"
              :bordered="false"
              class="chat-input"
            />
            <n-button v-if="!chatStore.streaming" type="primary" @click="handleSend" :disabled="!input.trim()">发送</n-button>
            <n-button v-else type="error" @click="chatStore.stopStreaming()">停止</n-button>
          </div>
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
/* 整体：横向 flex，侧边栏 + 主区 */
.chat-shell {
  display: flex;
  height: 100%;
  width: 100%;
  background: var(--bg-base);
}

/* 主区：纵向 flex（消息区 flex:1 + 输入栏同级） */
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  height: 100%;
}

/* 消息滚动区：flex:1 + minHeight:0（关键！让 flex 子项可收缩） */
.msg-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
}

/* 消息内容：居中限宽 960px（LobeChat 风格） */
.msg-inner {
  max-width: var(--chat-max-width);
  margin: 0 auto;
  padding: 24px 16px 16vh;  /* 底部留 16vh 让最后一条消息不被输入栏遮挡 */
}

/* ===== 空状态（LobeChat AgentHome 风格） ===== */
.welcome {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}
.welcome-spacer { flex: 1; }  /* 顶部弹簧把内容压到下半部 */
.welcome-content {
  display: flex; flex-direction: column; align-items: center;
  padding-bottom: max(4vh, 16px); gap: 12px;
}
.welcome-icon { font-size: 40px; }
.welcome-title { font-size: 22px; font-weight: 600; }
.welcome-desc { font-size: 14px; color: var(--text-tertiary); text-align: center; }
.suggestions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; max-width: 600px; margin-top: 8px; }
.suggestion {
  padding: 8px 16px; border-radius: 48px;  /* 药丸形 */
  background: var(--bg-surface); border: 1px solid var(--border-medium);
  color: var(--text-secondary); font-size: 13px; cursor: pointer;
  transition: opacity var(--transition);
}
.suggestion:hover { opacity: 0.85; border-color: var(--primary); color: var(--primary); }
.quick-nav { display: flex; gap: 8px; margin-top: 8px; }

/* ===== 消息行（LobeChat 风格） ===== */
.msg-row { padding: 4px 0; margin-bottom: 4px; }
.msg-row.user { display: flex; justify-content: flex-end; }

/* 用户气泡：有背景，圆角，LobeChat 风格 */
.user-bubble {
  background: var(--bubble-user);  /* rgba(255,255,255,0.08) */
  color: var(--text-primary);
  padding: 8px 12px;
  border-radius: var(--radius-md);  /* 12px */
  max-width: 75%;
  word-wrap: break-word;
  white-space: pre-wrap;
  font-size: 15px;
  line-height: 1.6;
}

/* assistant：无气泡背景，直接显示在聊天区（LobeChat 风格） */
.msg-agents { font-size: 12px; color: var(--text-tertiary); margin-bottom: 6px; }
.assistant-content {
  color: var(--text-primary);
  font-size: 15px;
  line-height: 1.6;
  max-width: 100%;
}
.cursor { color: var(--primary); animation: blink 1s infinite; }
@keyframes blink { 0%,50%{opacity:1} 51%,100%{opacity:0} }

/* ===== 输入栏：flex 同级，不 absolute ===== */
.input-area {
  flex-shrink: 0;  /* 不被压缩 */
  padding: 8px 16px 16px;
  background: var(--bg-base);
  border-top: 1px solid var(--border-subtle);
}
.input-container {
  max-width: var(--chat-max-width);  /* 与消息列同宽居中 */
  margin: 0 auto;
}
.agent-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
.input-row { display: flex; align-items: flex-end; gap: 8px; }
.chat-input {
  background: var(--bg-surface) !important;
  border-radius: var(--radius-md) !important;
  padding: 10px 16px !important;
  border: 1px solid var(--border-medium) !important;
  flex: 1;
}
.chat-input :deep(.n-input__textarea-el) { color: var(--text-primary) !important; }
</style>
