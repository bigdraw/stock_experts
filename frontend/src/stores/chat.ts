import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import apiClient from '../api/client'

export interface ChatMessageData {
  id?: number
  role: 'user' | 'assistant' | 'system'
  content: string
  agents_used?: string[]
  stocks_detected?: string[]
  meta?: Record<string, any> | null
  created_at?: string
  streaming?: boolean
  error?: boolean
}

export interface ChatSessionData {
  id: number
  title: string
  agent_ids: number[]
  type: 'chat' | 'debate'
  pinned: boolean
  last_message_at?: string
  messages?: ChatMessageData[]
}

export const useChatStore = defineStore('chat', () => {
  const sessions = ref<ChatSessionData[]>([])
  const currentSessionId = ref<number | null>(null)
  const messages = ref<ChatMessageData[]>([])
  const streaming = ref(false)
  let abortController: AbortController | null = null

  const currentSession = computed(() => sessions.value.find(s => s.id === currentSessionId.value) || null)

  async function loadSessions() {
    try {
      const res = await apiClient.get('/chat/sessions')
      sessions.value = res.data
      // 从 localStorage 恢复 currentSessionId
      const saved = localStorage.getItem('chat_session_id')
      if (saved && sessions.value.find(s => s.id === parseInt(saved))) {
        currentSessionId.value = parseInt(saved)
      } else if (sessions.value.length > 0) {
        currentSessionId.value = sessions.value[0].id
      }
    } catch (e) {
      console.error('loadSessions failed', e)
    }
  }

  async function createSession(title = '新对话', agentIds: number[] = []): Promise<number | null> {
    try {
      const res = await apiClient.post('/chat/sessions', { title, agent_ids: agentIds })
      sessions.value.unshift(res.data)
      currentSessionId.value = res.data.id
      localStorage.setItem('chat_session_id', String(res.data.id))
      messages.value = []
      return res.data.id
    } catch (e) {
      console.error('createSession failed', e)
      return null
    }
  }

  async function selectSession(id: number) {
    currentSessionId.value = id
    localStorage.setItem('chat_session_id', String(id))
    try {
      const res = await apiClient.get(`/chat/sessions/${id}`)
      if (res.data && !res.data.error) {
        messages.value = res.data.messages || []
      }
    } catch (e) {
      console.error('selectSession failed', e)
    }
  }

  async function deleteSession(id: number) {
    try {
      await apiClient.delete(`/chat/sessions/${id}`)
      sessions.value = sessions.value.filter(s => s.id !== id)
      if (currentSessionId.value === id) {
        currentSessionId.value = sessions.value.length > 0 ? sessions.value[0].id : null
        messages.value = []
      }
    } catch (e) {
      console.error('deleteSession failed', e)
    }
  }

  // 批量删除会话（管理模式多选）。逐个 DELETE（后端无批量端点），失败项忽略。
  async function deleteSessions(ids: number[]) {
    const ok: number[] = []
    await Promise.all(ids.map(async (id) => {
      try {
        await apiClient.delete(`/chat/sessions/${id}`)
        ok.push(id)
      } catch (e) {
        console.error('deleteSession failed', id, e)
      }
    }))
    if (ok.length) {
      const removed = new Set(ok)
      sessions.value = sessions.value.filter(s => !removed.has(s.id))
      if (currentSessionId.value !== null && removed.has(currentSessionId.value)) {
        currentSessionId.value = sessions.value.length > 0 ? sessions.value[0].id : null
        messages.value = []
      }
    }
    return ok
  }

  async function renameSession(id: number, title: string) {
    try {
      await apiClient.patch(`/chat/sessions/${id}`, { title })
      const s = sessions.value.find(s => s.id === id)
      if (s) s.title = title
    } catch (e) {
      console.error('renameSession failed', e)
    }
  }

  async function sendMessage(text: string, agentIds: number[] = []) {
    if (!currentSessionId.value) {
      const id = await createSession('新对话', agentIds)
      if (!id) return
    }
    const sessionId = currentSessionId.value!

    // 乐观追加 user 消息
    messages.value.push({ role: 'user', content: text })
    // 追加 assistant 占位
    const assistantMsg: ChatMessageData = { role: 'assistant', content: '', streaming: true }
    messages.value.push(assistantMsg)

    streaming.value = true
    abortController = new AbortController()

    try {
      const token = localStorage.getItem('token')
      const res = await fetch(`/api/v1/chat/sessions/${sessionId}/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ message: text, agent_ids: agentIds }),
        signal: abortController.signal,
      })

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
            if (eventType === 'text' && data.content) {
              assistantMsg.content += data.content
            } else if (eventType === 'stop') {
              assistantMsg.streaming = false
            } else if (eventType === 'error') {
              assistantMsg.content += `\n\n⚠️ ${data.message}`
              assistantMsg.streaming = false
            }
          } catch (e) {
            console.error('SSE parse error', e)
          }
        }
      }
      assistantMsg.streaming = false

      // 更新侧边栏标题（如果是首条消息自动生成）
      const session = sessions.value.find(s => s.id === sessionId)
      if (session && session.title === '新对话') {
        session.title = text.slice(0, 20) + (text.length > 20 ? '…' : '')
      }
    } catch (e: any) {
      if (e.name === 'AbortError') {
        assistantMsg.streaming = false
      } else {
        assistantMsg.content += `\n\n⚠️ ${e.message}`
        assistantMsg.streaming = false
        assistantMsg.error = true
      }
    } finally {
      streaming.value = false
      abortController = null
    }
  }

  // 直播辩论：在 chat 会话里流式渲染多 agent 气泡（agent_start/token/done + summary_*）。
  // 后端 POST /debate/start-stream 即建 type=debate 会话并流式产出事件。
  async function startDebate(agentIds: number[], targetCode: string, targetName: string, rounds: number) {
    messages.value = []
    streaming.value = true
    abortController = new AbortController()
    const agentMsgIdx = new Map<string, number>()  // "round_num:agent_id" → messages 下标
    let summaryIdx = -1
    let sessionId: number | null = null

    try {
      const token = localStorage.getItem('token')
      const res = await fetch('/api/v1/debate/start-stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ agent_ids: agentIds, target_type: 'stock', target_id: targetCode, rounds }),
        signal: abortController.signal,
      })
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
          const ev = lines[0]?.replace('event: ', '') || ''
          const dataStr = lines[1]?.replace('data: ', '') || '{}'
          try {
            const data = JSON.parse(dataStr)
            if (ev === 'session') {
              const sid: number = data.session_id
              sessionId = sid
              currentSessionId.value = sid
              localStorage.setItem('chat_session_id', String(sid))
              if (!sessions.value.find(s => s.id === sid)) {
                sessions.value.unshift({
                  id: sid, title: `辩论：${targetName}(${targetCode})`,
                  agent_ids: agentIds, type: 'debate', pinned: false,
                })
              }
            } else if (ev === 'factbook') {
              messages.value.push({ role: 'system', content: data.content, meta: { round_type: 'factbook' } })
            } else if (ev === 'agent_start') {
              messages.value.push({
                role: 'assistant', content: '', streaming: true,
                agents_used: [data.agent_name],
                meta: { round_type: data.round_type, round_num: data.round_num, agent_id: data.agent_id, agent_name: data.agent_name },
              })
              agentMsgIdx.set(`${data.round_num}:${data.agent_id}`, messages.value.length - 1)
            } else if (ev === 'agent_token') {
              const i = agentMsgIdx.get(`${data.round_num}:${data.agent_id}`)
              if (i != null) messages.value[i].content += data.delta
            } else if (ev === 'agent_done') {
              const i = agentMsgIdx.get(`${data.round_num}:${data.agent_id}`)
              if (i != null) { messages.value[i].content = data.content; messages.value[i].streaming = false }
            } else if (ev === 'summary_start') {
              messages.value.push({
                role: 'assistant', content: '', streaming: true,
                agents_used: ['总结'], meta: { round_type: 'summary' },
              })
              summaryIdx = messages.value.length - 1
            } else if (ev === 'summary_token') {
              if (summaryIdx >= 0) messages.value[summaryIdx].content += data.delta
            } else if (ev === 'summary_done') {
              if (summaryIdx >= 0) { messages.value[summaryIdx].content = data.content; messages.value[summaryIdx].streaming = false }
            } else if (ev === 'error') {
              messages.value.push({ role: 'system', content: `⚠️ ${data.message || '辩论出错'}`, meta: { round_type: 'error' } })
            }
          } catch (e) {
            console.error('Debate SSE parse error', e)
          }
        }
      }
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        messages.value.push({ role: 'system', content: `⚠️ 辩论失败：${e.message}`, meta: { round_type: 'error' } })
      }
    } finally {
      streaming.value = false
      abortController = null
      if (sessionId) await loadSessions()  // 刷新侧栏（标题/最新态）
    }
  }

  async function retryLastMessage(agentIds: number[] = []) {
    // Find last user message, remove the failed assistant reply, resend
    const lastUserIdx = [...messages.value].reverse().findIndex(m => m.role === 'user')
    if (lastUserIdx < 0) return
    const lastUser = messages.value[messages.value.length - 1 - lastUserIdx]
    // Remove everything after the last user message (failed assistant reply)
    messages.value = messages.value.slice(0, messages.value.length - lastUserIdx)
    // Resend
    await sendMessage(lastUser.content, agentIds)
  }

  function stopStreaming() {
    abortController?.abort()
    streaming.value = false
  }

  return {
    sessions, currentSessionId, currentSession, messages, streaming,
    loadSessions, createSession, selectSession, deleteSession, deleteSessions, renameSession,
    sendMessage, startDebate, stopStreaming, retryLastMessage,
  }
})
