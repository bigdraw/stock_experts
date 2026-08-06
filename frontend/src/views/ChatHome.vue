<template>
  <div class="chat-shell">
    <!-- 侧边栏（移动端隐藏） -->
    <div class="desktop-only"><SessionSidebar /></div>

    <!-- 主区：纵向 flex，消息区 flex:1 滚动，输入栏同级沉底 -->
    <div class="chat-main">
      <!-- 消息区 -->
      <div class="msg-scroll" ref="msgList" @scroll="onMsgScroll">
        <div class="msg-inner">
          <!-- 空状态 -->
          <div v-if="!chatStore.messages.length" class="welcome">
            <div class="welcome-spacer" />
            <div class="welcome-content">
              <div class="welcome-icon">⚡</div>
              <h2 class="welcome-title">嗨～我是小雷</h2>
              <p class="welcome-desc">问我任何一只股票，我来替你看数据、找大师辩论 ⚡</p>
              <div class="suggestions">
                <button v-for="s in suggestions" :key="s" class="suggestion" @click="quickFill(s)">{{ s }}</button>
              </div>
              <div class="quick-nav">
                <n-button size="small" secondary @click="$router.push('/stocks')">股票</n-button>
                <n-button size="small" secondary @click="$router.push('/portfolios')">组合</n-button>
                <n-button size="small" secondary @click="$router.push('/backtest')">回测</n-button>
                <n-button size="small" type="primary" secondary @click="showDebateModal = true">⚖️ 辩论</n-button>
              </div>
            </div>
          </div>

          <!-- 消息列表（meta-aware：辩论 agent 气泡 / 总结 / FactBook / 普通 chat） -->
          <template v-for="(msg, i) in chatStore.messages" :key="i">
            <!-- 用户消息 -->
            <div v-if="msg.role === 'user'" class="msg-row user">
              <div class="bubble user-bubble">{{ msg.content }}</div>
            </div>
            <!-- FactBook 输入事实基础（可折叠，让用户看到喂给 agent 的数据） -->
            <div v-else-if="msg.meta?.round_type === 'factbook'" class="msg-row">
              <div class="factbook-panel">
                <div class="factbook-head" @click="toggleFactbook(i)">
                  <span>📊 输入事实基础（事实 agent 消化，所有 agent 共享）{{ msg.streaming ? '· 消化中…' : '' }}</span>
                  <span class="factbook-toggle">{{ isFactbookOpen(i) ? '收起 ▲' : '展开 ▼' }}</span>
                </div>
                <div v-if="isFactbookOpen(i)" class="factbook-body">
                  <ThinkingDots v-if="msg.streaming && !msg.content" text="事实 agent 正在消化原始数据…" />
                  <template v-else>
                    <MarkdownRenderer v-if="msg.content" :content="msg.content" />
                    <span v-if="msg.streaming" class="cursor">▋</span>
                  </template>
                </div>
              </div>
            </div>
            <!-- FactBook 采集进度（正在获取价值分析/K线/行业/宏观/市场状态…） -->
            <div v-else-if="msg.meta?.round_type === 'collecting'" class="msg-row">
              <div class="collecting-status"><ThinkingDots :text="msg.content" /></div>
            </div>
            <!-- 错误提示 -->
            <div v-else-if="msg.meta?.round_type === 'error'" class="msg-row">
              <div class="error-bubble">{{ msg.content }}</div>
            </div>
            <!-- 信息提示（NL 恢复的状态回复：在执行/重试中/已完成 等） -->
            <div v-else-if="msg.meta?.round_type === 'info'" class="msg-row">
              <div class="info-bubble">{{ msg.content }}</div>
            </div>
            <!-- 数据检验报告面板（可选，辩论前数据检验agent产出） -->
            <div v-else-if="msg.meta?.round_type === 'validation'" class="msg-row">
              <div class="factbook-panel">
                <div class="factbook-head" @click="toggleFactbook(i)">
                  <span>✅ 数据检验报告{{ msg.streaming ? ' · 检验中…' : '' }}</span>
                  <span class="factbook-toggle">{{ isFactbookOpen(i) ? '收起 ▲' : '展开 ▼' }}</span>
                </div>
                <div v-if="isFactbookOpen(i)" class="factbook-body">
                  <ReasoningPanel v-if="reasoningText(msg)" :reasoning="reasoningText(msg)" :streaming="msg.streaming" :has-content="!!msg.content" />
                  <ThinkingDots v-if="msg.streaming && !msg.content && !reasoningText(msg)" text="数据检验中…" />
                  <MarkdownRenderer v-else-if="msg.content" :content="msg.content" />
                  <span v-if="msg.streaming && msg.content" class="cursor">▋</span>
                </div>
              </div>
            </div>
            <!-- 检索结果面板（多 agent @mention 时 tavily 检索的可折叠展示） -->
            <div v-else-if="msg.meta?.round_type === 'search'" class="msg-row">
              <div class="factbook-panel">
                <div class="factbook-head" @click="toggleFactbook(i)">
                  <span>🔍 检索结果{{ msg.streaming ? ' · 检索中…' : '' }}</span>
                  <span class="factbook-toggle">{{ isFactbookOpen(i) ? '收起 ▲' : '展开 ▼' }}</span>
                </div>
                <div v-if="isFactbookOpen(i)" class="factbook-body">
                  <MarkdownRenderer v-if="msg.content" :content="msg.content" />
                </div>
              </div>
            </div>
            <!-- 辩论 agent 气泡（分析/质疑/回应） -->
            <div v-else-if="msg.meta?.round_type && msg.meta.round_type !== 'summary'" class="msg-row assistant">
              <div class="debate-bubble" :style="{ borderLeftColor: agentColor(msg.meta.agent_name || '') }">
                <div class="debate-head">
                  <span class="debate-agent" :style="{ color: agentColor(msg.meta.agent_name || '') }">{{ msg.meta.agent_name }}</span>
                  <n-tag size="tiny" round>{{ roundLabel(msg.meta.round_type) }} · 第{{ msg.meta.round_num }}轮</n-tag>
                </div>
                <ReasoningPanel v-if="reasoningText(msg)" :reasoning="reasoningText(msg)" :streaming="msg.streaming" :has-content="!!msg.content" />
                <div class="assistant-content">
                  <ThinkingDots v-if="msg.streaming && !msg.content && !reasoningText(msg)" :text="`${msg.meta.agent_name} 思考中…`" />
                  <MarkdownRenderer v-else-if="msg.content" :content="msg.content" />
                  <span v-if="msg.streaming && msg.content" class="cursor">▋</span>
                </div>
                <div v-if="msg.error && !msg.streaming" class="retry-bar">
                  <n-tag size="tiny" type="error" round>调用失败</n-tag>
                  <n-button size="small" type="primary" secondary :loading="chatStore.currentSessionStreaming" @click="retryDebate">原地重试</n-button>
                </div>
              </div>
            </div>
            <!-- 总结气泡 -->
            <div v-else-if="msg.meta?.round_type === 'summary'" class="msg-row assistant">
              <div class="summary-bubble">
                <div class="summary-head">📝 辩论总结</div>
                <ReasoningPanel v-if="reasoningText(msg)" :reasoning="reasoningText(msg)" :streaming="msg.streaming" :has-content="!!msg.content" />
                <div class="assistant-content">
                  <ThinkingDots v-if="msg.streaming && !msg.content && !reasoningText(msg)" text="总结中…" />
                  <MarkdownRenderer v-else-if="msg.content" :content="msg.content" />
                  <span v-if="msg.streaming && msg.content" class="cursor">▋</span>
                </div>
                <div v-if="msg.error && !msg.streaming" class="retry-bar">
                  <n-tag size="tiny" type="error" round>总结失败</n-tag>
                  <n-button size="small" type="primary" secondary :loading="chatStore.currentSessionStreaming" @click="retryDebate">原地重试</n-button>
                </div>
              </div>
            </div>
            <!-- 普通 chat assistant 气泡 -->
            <div v-else class="msg-row assistant">
              <div v-if="msg.agents_used?.length" class="msg-agents">{{ msg.agents_used.map(a => '@'+a).join(' ') }}</div>
              <ReasoningPanel v-if="reasoningText(msg)" :reasoning="reasoningText(msg)" :streaming="msg.streaming" :has-content="!!msg.content" />
              <div class="assistant-content">
                <ThinkingDots v-if="msg.streaming && !msg.content && !reasoningText(msg)" />
                <MarkdownRenderer v-else-if="msg.content" :content="msg.content" />
                <span v-if="msg.streaming && msg.content" class="cursor">▋</span>
              </div>
              <div v-if="msg.error && !msg.streaming" class="retry-bar">
                <n-button size="small" type="primary" secondary @click="handleRetry">重试</n-button>
              </div>
            </div>
          </template>
        </div>
        <!-- 回到底部浮钮：用户上滚查看时显示，点击回到最新 -->
        <transition name="fade">
          <button v-if="!autoScroll && chatStore.messages.length" class="scroll-bottom-btn" @click="scrollToBottom">↓</button>
        </transition>
      </div>

      <!-- 输入栏 -->
      <div class="input-area" ref="inputAreaRef">
        <div class="input-container">
          <div class="input-toolbar">
            <n-button size="small" tertiary @click="showDebateModal = true">⚖️ 开始辩论</n-button>
            <div v-if="selectedAgents.length" class="agent-tags">
              <n-tag v-for="a in selectedAgents" :key="a.id" closable size="small" @close="removeAgent(a.id)" type="info">{{ '@'+a.name }}</n-tag>
            </div>
          </div>
          <div class="input-row input-row-mention">
            <div class="mention-wrap">
              <n-input
                v-model:value="input"
                ref="inputRef"
                type="textarea"
                :autosize="{ minRows: 1, maxRows: 5 }"
                placeholder="输入消息… 输入 @ 触发 agent 选择"
                @keydown="onInputKey"
                @update:value="onInputChange"
                :bordered="false"
                class="chat-input"
              />
              <!-- @mention 浮动下拉 -->
              <div v-if="mentionOpen" class="mention-pop">
                <div v-for="(a, idx) in mentionMatches" :key="a.id"
                  :class="['mention-item', { active: idx === mentionIdx }]"
                  @click="selectMention(a)" @mouseenter="mentionIdx = idx">
                  <span class="mention-name">{{ a.name }}</span>
                  <span class="mention-desc">{{ a.type }}</span>
                </div>
                <div v-if="!mentionMatches.length" class="mention-empty">无匹配 agent</div>
              </div>
            </div>
            <n-button v-if="!chatStore.currentSessionStreaming" type="primary" @click="handleSend" :disabled="!input.trim()">发送</n-button>
            <n-button v-else type="error" @click="chatStore.stopStreaming()">停止</n-button>
          </div>
        </div>
      </div>
    </div>

    <!-- 辩论发起弹窗：选 agent + 标的 + 轮数 → 直播进当前 chat 会话 -->
    <n-modal v-model:show="showDebateModal" preset="card" title="开始多 Agent 辩论" style="max-width: 560px;">
      <n-form>
        <n-form-item label="参与 Agent（≥2）">
          <n-select v-model:value="debateAgentIds" multiple filterable :options="agentOptions"
            placeholder="选择投资大师" />
        </n-form-item>
        <n-form-item label="分析标的">
          <n-auto-complete
            v-model:value="debateTargetInput"
            :options="debateStockOptions"
            :loading="debateSearching"
            placeholder="输入代码/名称/拼音/首字母（如 600519 / 茅台 / mtfy）"
            clearable
            @update:value="onDebateSearch"
            @select="onDebateSelect"
          />
          <div v-if="debateSelectedStock" class="debate-selected">
            已选：<n-tag size="small" type="info" round>{{ debateSelectedStock.code }}</n-tag>
            <span class="debate-selected-name">{{ debateSelectedStock.name }}</span>
          </div>
        </n-form-item>
        <n-form-item label="辩论轮数">
          <n-input-number v-model:value="debateRounds" :min="2" :max="5" />
        </n-form-item>
        <n-form-item label="数据检验 agent">
          <n-switch v-model:value="validateData" />
          <span style="margin-left:8px; font-size:12px; color:var(--text-tertiary)">辩论前由数据检验agent检查完整性/时效性/逻辑一致性（可选）</span>
        </n-form-item>
        <div class="debate-actions">
          <n-button @click="showDebateModal = false">取消</n-button>
          <n-button type="primary" :disabled="debateAgentIds.length < 2 || !debateCode" :loading="debateSubmitting" @click="startDebate">开始辩论</n-button>
        </div>
      </n-form>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import { NButton, NTag, NInput, NModal, NForm, NFormItem, NSelect, NAutoComplete, NInputNumber, NSwitch } from 'naive-ui'
import { useChatStore } from '../stores/chat'
import { agentColor } from '../composables/useAgentColor'
import ReasoningPanel from '../components/chat/ReasoningPanel.vue'
import ThinkingDots from '../components/chat/ThinkingDots.vue'
import SessionSidebar from '../components/chat/SessionSidebar.vue'
import MarkdownRenderer from '../components/chat/MarkdownRenderer.vue'
import apiClient from '../api/client'
import { stocksApi } from '../api'
import type { Agent, Stock } from '../types'

const chatStore = useChatStore()
const route = useRoute()
const input = ref('')
// 是否贴底：用户主动上滚（距底 >80px）则不强制拉回，方便回看前面的内容
const autoScroll = ref(true)
const msgList = ref<HTMLElement | null>(null)
const inputAreaRef = ref<HTMLElement | null>(null)
const agentList = ref<Agent[]>([])
const selectedAgents = ref<Agent[]>([])
const suggestions = ['分析 600519 的估值和盈利能力', '@巴菲特 茅台值不值得买', '分析我的投资组合风险']

// @mention 自动补全：输入框打 @ → 浮动 agent 下拉，↑↓Enter/点击选中插入
const inputRef = ref<any>(null)
const mentionOpen = ref(false)
const mentionMatches = ref<Agent[]>([])
const mentionIdx = ref(0)
const mentionAt = ref(0)  // @ 在输入串的位置（用于替换）

function textareaEl(): HTMLTextAreaElement | null {
  const el = inputRef.value?.$el as HTMLElement | undefined
  return el ? el.querySelector('textarea') : null
}
function closeMention() { mentionOpen.value = false; mentionIdx.value = 0 }
function onInputChange(val: string) {
  const ta = textareaEl()
  if (!ta) { closeMention(); return }
  const caret = ta.selectionStart ?? val.length
  const before = val.slice(0, caret)
  const atIdx = before.lastIndexOf('@')
  if (atIdx < 0 || (atIdx > 0 && !/\s/.test(before[atIdx - 1]))) { closeMention(); return }
  const query = before.slice(atIdx + 1)
  if (/\s/.test(query)) { closeMention(); return }
  mentionAt.value = atIdx
  mentionMatches.value = agentList.value
    .filter(a => a.name.toLowerCase().includes(query.toLowerCase()))
  mentionIdx.value = 0
  mentionOpen.value = mentionMatches.value.length > 0
}
function selectMention(a: Agent) {
  const ta = textareaEl()
  const caret = ta?.selectionStart ?? input.value.length
  const atIdx = mentionAt.value
  const before = input.value.slice(0, atIdx)
  const after = input.value.slice(caret)
  input.value = before + '@' + a.name + ' ' + after
  closeMention()
  nextTick(() => {
    const t = textareaEl()
    if (t) { const pos = atIdx + a.name.length + 2; t.setSelectionRange(pos, pos); t.focus() }
  })
}
function onInputKey(e: KeyboardEvent) {
  if (mentionOpen.value) {
    if (e.key === 'ArrowDown') { e.preventDefault(); mentionIdx.value = Math.min(mentionIdx.value + 1, mentionMatches.value.length - 1) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); mentionIdx.value = Math.max(mentionIdx.value - 1, 0) }
    else if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); if (mentionMatches.value[mentionIdx.value]) selectMention(mentionMatches.value[mentionIdx.value]) }
    else if (e.key === 'Escape') { closeMention() }
    return
  }
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); handleSend() }
}
function parseMentions(text: string): number[] {
  // 按全名匹配（agent 名含空格如"巴菲特 (Warren Buffett)"，正则 @\S+ 只取到空格前会漏）
  return agentList.value.filter(a => text.includes('@' + a.name)).map(a => a.id)
}

const agentOptions = computed(() => agentList.value.map(a => ({ label: a.name, value: a.id })))

const ROUND_LABELS: Record<string, string> = { analysis: '独立分析', challenge: '质疑', response: '回应', summary: '总结', factbook: '事实基础' }
function roundLabel(t: string) { return ROUND_LABELS[t] || t }

// FactBook 折叠态
const factbookOpen = ref<Record<number, boolean>>({})
function toggleFactbook(i: number) { factbookOpen.value[i] = !(factbookOpen.value[i] ?? true) }
function isFactbookOpen(i: number): boolean { return factbookOpen.value[i] ?? true }

// reasoningText helper（ReasoningPanel 组件管理自己的折叠态，这里只提取 reasoning 文本）
function reasoningText(msg: any): string { return msg.reasoning || msg.meta?.reasoning || '' }

// 辩论弹窗
const showDebateModal = ref(false)
const debateAgentIds = ref<number[]>([])
const debateTargetInput = ref('')
const debateStockOptions = ref<any[]>([])
const debateSearching = ref(false)
const debateSelectedStock = ref<Stock | null>(null)
const debateRounds = ref(3)
const validateData = ref(false)
// ISSUE-030: local submit flag for the debate modal only — brief, just for
// click feedback. NOT tied to global streaming so a 2nd debate can start while
// another streams in parallel (each debate owns its own session/stream).
const debateSubmitting = ref(false)
let debateSearchTimeout: ReturnType<typeof setTimeout> | null = null
let debateSelecting = false

const debateCode = computed(() => debateSelectedStock.value?.code || '')

function onDebateSearch(value: string) {
  if (debateSearchTimeout) clearTimeout(debateSearchTimeout)
  // 选中触发的同步 update（值=code），跳过：保留已选、不重搜
  if (debateSelecting) { debateSelecting = false; return }
  debateSelectedStock.value = null
  if (!value || !value.trim()) { debateStockOptions.value = []; return }
  debateSearchTimeout = setTimeout(async () => {
    debateSearching.value = true
    try {
      const res = await stocksApi.search(value.trim(), 20)
      debateStockOptions.value = (res.data || []).map((s: Stock) => ({ label: `${s.code} ${s.name}`, value: s.code, stock: s }))
    } catch { debateStockOptions.value = [] }
    finally { debateSearching.value = false }
  }, 300)
}
function onDebateSelect(code: string) {
  debateSelecting = true
  const opt = debateStockOptions.value.find(o => o.value === code)
  if (opt?.stock) { debateSelectedStock.value = opt.stock; debateTargetInput.value = opt.stock.code }
}

async function startDebate() {
  const code = debateSelectedStock.value?.code
  const name = debateSelectedStock.value?.name || code || ''
  if (debateAgentIds.value.length < 2 || !code) return
  if (debateSubmitting.value) return  // prevent double-click
  showDebateModal.value = false
  debateSubmitting.value = true
  // Fire-and-forget: startDebate runs the whole stream but we don't await it
  // here — the per-session streaming flag + ThinkingDots drive the in-flight
  // UI, and not awaiting lets the user start/switch debates in parallel.
  chatStore.startDebate(debateAgentIds.value, code, name, debateRounds.value, validateData.value)
    .catch(e => console.error('startDebate failed', e))
    .finally(() => { debateSubmitting.value = false })
  await scrollToBottom()
}

// ResizeObserver：跟踪输入区实际高度→设 CSS 变量→msg-inner 底部 padding 动态跟随。
// 输入区 absolute 脱离 flex 流后，msg-scroll 高度恒定（不再因 textarea 增高而缩小→抖动），
// 但 msg-inner 底部需留出输入区高度的空间（否则最后一条消息被输入区遮挡）。
let _inputResizeObserver: ResizeObserver | null = null

onMounted(async () => {
  await chatStore.loadSessions()
  const sid = route.params.sessionId
  if (sid) await chatStore.selectSession(parseInt(sid as string))
  else if (chatStore.currentSessionId) await chatStore.selectSession(chatStore.currentSessionId)
  try { agentList.value = (await apiClient.get('/chat/agents')).data } catch {}
  if (route.query.debate === '1') showDebateModal.value = true

  if (inputAreaRef.value) {
    const updateInputHeight = () => {
      if (inputAreaRef.value) {
        document.documentElement.style.setProperty(
          '--input-area-h', `${inputAreaRef.value.offsetHeight}px`
        )
      }
    }
    updateInputHeight()
    _inputResizeObserver = new ResizeObserver(updateInputHeight)
    _inputResizeObserver.observe(inputAreaRef.value)
  }
})

onUnmounted(() => {
  if (_inputResizeObserver) { _inputResizeObserver.disconnect(); _inputResizeObserver = null }
})

function removeAgent(id: number) { selectedAgents.value = selectedAgents.value.filter(a => a.id !== id) }
function quickFill(text: string) { input.value = text }

async function handleRetry() {
  await chatStore.retryLastMessage(selectedAgents.value.map(a => a.id))
  await scrollToBottom()
}
async function retryDebate() {
  await chatStore.resumeDebate()
  await scrollToBottom()
}
async function handleSend() {
  if (!input.value.trim()) return
  const text = input.value; input.value = ''
  closeMention()
  // NL debate recovery: a short 继续/重试 phrase on a debate session is
  // intercepted — the store checks state (streaming / paused / completed) and
  // replies with a status bubble, optionally firing resumeDebate. Returns
  // true if handled; otherwise the text goes to the LLM as a normal message.
  if (chatStore.getContinueIntent(text) && await chatStore.continueOrRetryDebate(text)) {
    await scrollToBottom()
    return
  }
  // 优先用 @mention 解析出的 agent ids；否则用已选 selectedAgents
  const ids = parseMentions(text)
  const agentIds = ids.length ? ids : selectedAgents.value.map(a => a.id)
  await chatStore.sendMessage(text, agentIds)
  await scrollToBottom()
}
// 滚动监听：判断用户是否贴底。距底 < 80px 视为贴底（流式时自动跟随），
// 否则用户主动上滚了——不再强制拉回，让其自由查看前面的内容。
function onMsgScroll() {
  const el = msgList.value
  if (!el) return
  autoScroll.value = el.scrollHeight - el.scrollTop - el.clientHeight < 80
}
// rAF 节流：多个 token delta 合并到一帧一次滚动，避免每 token scrollTop=scrollHeight 跳变 → 画面抖动。
let _scrollPending = false
function maybeScrollToBottom() {
  if (!autoScroll.value) return
  if (_scrollPending) return
  _scrollPending = true
  requestAnimationFrame(() => {
    _scrollPending = false
    if (msgList.value) msgList.value.scrollTop = msgList.value.scrollHeight
  })
}
// 强制滚到底（用户主动操作：发消息/新会话/重试）
async function scrollToBottom() {
  autoScroll.value = true
  await nextTick()
  if (msgList.value) msgList.value.scrollTop = msgList.value.scrollHeight
}
watch(() => chatStore.messages.length, () => maybeScrollToBottom())
watch(() => chatStore.messages.at(-1)?.content, () => maybeScrollToBottom())
</script>

<style scoped>
.chat-shell { display: flex; height: 100%; width: 100%; background: var(--bg-base); }
.chat-main { flex: 1; display: flex; flex-direction: column; min-width: 0; height: 100%; position: relative; }
.msg-scroll { flex: 1; min-height: 0; overflow-y: auto; overflow-x: hidden; position: relative; scroll-behavior: smooth; contain: layout; }
.scroll-bottom-btn {
  position: sticky; bottom: 12px; margin-left: auto; margin-right: 12px;
  width: 36px; height: 36px; border-radius: var(--radius-pill); border: 1px solid var(--border-medium);
  background: var(--bg-elevated); color: var(--text-primary); cursor: pointer; font-size: 18px;
  display: flex; align-items: center; justify-content: center;
  box-shadow: var(--shadow-soft); transition: opacity var(--transition);
}
.scroll-bottom-btn:hover { border-color: var(--primary); color: var(--primary); }
.fade-enter-active, .fade-leave-active { transition: opacity var(--transition); }
.fade-enter-from, .fade-leave-to { opacity: 0; }
.msg-inner { max-width: var(--chat-max-width); margin: 0 auto; padding: 20px 16px calc(var(--input-area-h, 80px) + 16px); display: flex; flex-direction: column; min-height: 100%; box-sizing: border-box; }

/* 欢迎页：撑满滚动区、内容垂直居中（不再浮在上中部留大块空白） */
.welcome { flex: 1; display: flex; flex-direction: column; justify-content: center; }
.welcome-content { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 16px 0; }
.welcome-icon { font-size: 40px; }
.welcome-title { font-size: 22px; font-weight: var(--fw-semibold); }
.welcome-desc { font-size: 14px; color: var(--text-tertiary); text-align: center; }
.suggestions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; max-width: 600px; margin-top: 8px; }
.suggestion {
  padding: 8px 16px; border-radius: var(--radius-pill); background: var(--bg-surface); border: 1px solid var(--border-medium);
  color: var(--text-secondary); font-size: var(--fs-label); cursor: pointer; transition: opacity var(--transition);
}
.suggestion:hover { opacity: 0.85; border-color: var(--primary); color: var(--primary); }
.quick-nav { display: flex; gap: 8px; margin-top: 8px; }

/* 消息行：拉大间距，避免气泡边框贴边"踩脚" */
.msg-row { padding: 2px 0; margin-bottom: 10px; }
.msg-row.user { display: flex; justify-content: flex-end; }
.user-bubble {
  background: var(--bubble-user); color: var(--text-primary); padding: 10px 14px;
  border-radius: var(--radius-md); max-width: 75%; word-wrap: break-word; white-space: pre-wrap;
  font-size: var(--fs-body); line-height: 1.6;
}
.msg-agents { font-size: var(--fs-meta); color: var(--text-tertiary); margin-bottom: 6px; }
.assistant-content { color: var(--text-primary); font-size: var(--fs-body); line-height: 1.6; max-width: 100%; }
/* .reasoning-panel / .thinking / .think-dot 移入 ReasoningPanel.vue + ThinkingDots.vue 组件 */
.cursor { color: var(--primary); animation: softPulse 1s infinite; }
.retry-bar { margin-top: 8px; display: flex; align-items: center; gap: 8px; }

/* 辩论 agent 气泡：左侧色条 + agent 名 + 轮次标签；拉大内边距与下间距 */
.debate-bubble {
  border-left: 3px solid var(--primary); background: var(--bg-surface);
  border-radius: var(--radius-md); padding: 12px 16px; margin-bottom: 12px;
}
.debate-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.debate-agent { font-weight: var(--fw-bold); font-size: 14px; }

/* 总结气泡：与上方气泡拉开距离，加左边色条与 agent 气泡呼应 */
.summary-bubble {
  border: 1px solid var(--border-medium); border-left: 3px solid var(--primary);
  background: var(--bg-elevated); border-radius: var(--radius-md);
  padding: 14px 16px; margin: 16px 0 12px;
}
.summary-head { font-weight: var(--fw-bold); font-size: 14px; margin-bottom: 10px; color: var(--primary); }

/* FactBook 折叠面板：与上下气泡拉开距离 */
.factbook-panel {
  border: 1px dashed var(--border-medium); border-radius: var(--radius-md);
  background: var(--bg-surface); margin: 12px 0; overflow: hidden;
}
.factbook-head {
  display: flex; justify-content: space-between; align-items: center; cursor: pointer;
  padding: 10px 14px; font-size: var(--fs-label); color: var(--text-secondary); font-weight: var(--fw-semibold);
}
.factbook-head:hover { background: var(--bg-elevated); }
.factbook-toggle { font-size: var(--fs-meta); color: var(--primary); }
.factbook-body { padding: 10px 14px 14px; max-height: 420px; overflow-y: auto; border-top: 1px solid var(--border-subtle); }

.collecting-status { padding: 8px 12px; }
.error-bubble {
  background: var(--error-tint); border: 1px solid var(--error);
  color: var(--error); padding: 8px 12px; border-radius: var(--radius-md); font-size: 14px;
}
.info-bubble {
  background: var(--accent-tint); border: 1px solid var(--accent);
  color: var(--text-primary); padding: 8px 12px; border-radius: var(--radius-md); font-size: 14px;
}

.input-area { position: absolute; bottom: 0; left: 0; right: 0; z-index: 10; padding: 8px 16px 16px; background: var(--bg-base); border-top: 1px solid var(--border-subtle); }
.input-container { max-width: var(--chat-max-width); margin: 0 auto; }
.input-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.agent-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.input-row { display: flex; align-items: flex-end; gap: 8px; }
.input-row-mention { position: relative; }
.mention-wrap { flex: 1; position: relative; }
.mention-pop {
  position: absolute; bottom: 100%; left: 0; right: 0; margin-bottom: 4px;
  background: var(--bg-elevated); border: 1px solid var(--border-medium); border-radius: var(--radius-md);
  box-shadow: var(--shadow-lift); max-height: 240px; overflow-y: auto; z-index: 100;
}
.mention-item { display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; cursor: pointer; }
.mention-item:hover, .mention-item.active { background: var(--bg-surface); }
.mention-name { font-size: 14px; font-weight: var(--fw-semibold); color: var(--text-primary); }
.mention-desc { font-size: 11px; color: var(--text-tertiary); }
.mention-empty { padding: 12px; text-align: center; color: var(--text-tertiary); font-size: 13px; }
.chat-input {
  background: var(--bg-surface) !important; border-radius: var(--radius-md) !important;
  padding: 10px 16px !important; border: 1px solid var(--border-medium) !important; flex: 1;
}
.chat-input :deep(.n-input__textarea-el) { color: var(--text-primary) !important; }

.debate-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
.debate-selected { margin-top: 6px; font-size: 13px; color: var(--text-secondary); display: flex; align-items: center; gap: 6px; }
.debate-selected-name { font-weight: var(--fw-semibold); color: var(--text-primary); }
</style>
