import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import apiClient from '../api/client'

export interface ChatMessageData {
  id?: number
  role: 'user' | 'assistant' | 'system'
  content: string
  agents_used?: string[]
  stocks_detected?: string[]
  created_at?: string
  streaming?: boolean
}

export interface ChatSessionData {
  id: number
  title: string
  agent_ids: number[]
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
      }
    } finally {
      streaming.value = false
      abortController = null
    }
  }

  function stopStreaming() {
    abortController?.abort()
    streaming.value = false
  }

  return {
    sessions, currentSessionId, currentSession, messages, streaming,
    loadSessions, createSession, selectSession, deleteSession, renameSession,
    sendMessage, stopStreaming,
  }
})
