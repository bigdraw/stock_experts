import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import apiClient, { handleStreamAuthFailure } from '../api/client'

export interface ChatMessageData {
  id?: number
  role: 'user' | 'assistant' | 'system'
  content: string
  reasoning?: string  // 思考链（enable_thinking，与正文分开，灰色可折叠展示）
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
  // 按 sessionId 分缓冲：辩论流式写自己的 buffer，切会话只换可见视图，
  // 互不干扰（修"辩论 token 灌进别的会话气泡 + 索引错位"的状态隔离 bug）。
  const messagesBySession = ref<Record<number, ChatMessageData[]>>({})
  function bufOf(sid: number): ChatMessageData[] {
    if (!messagesBySession.value[sid]) messagesBySession.value[sid] = []
    return messagesBySession.value[sid]
  }
  // 可见消息 = 当前会话的缓冲
  const messages = computed<ChatMessageData[]>(() =>
    currentSessionId.value != null ? (messagesBySession.value[currentSessionId.value] || []) : []
  )
  // Per-session streaming state (ISSUE-030 fix): a single global `streaming`
  // flag + single abortController serialized every stream (couldn't start a
  // 2nd debate while one ran) AND let selectSession overwrite an in-flight
  // buffer on switch-back (live tokens then wrote to an orphaned array →
  // "messages disappear until I switch back and an agent renders"). Now each
  // session tracks its own streaming flag + AbortController, so debates run in
  // parallel and switching sessions never clobbers a live buffer.
  const streamingSessions = ref<Record<number, boolean>>({})
  const abortControllers = new Map<number, AbortController>()
  const streaming = computed(() => Object.values(streamingSessions.value).some(Boolean))
  const currentSessionStreaming = computed(
    () => currentSessionId.value != null && !!streamingSessions.value[currentSessionId.value]
  )

  const currentSession = computed(() => sessions.value.find(s => s.id === currentSessionId.value) || null)

  async function loadSessions() {
    try {
      const res = await apiClient.get('/chat/sessions')
      sessions.value = res.data
      // Only adopt a current session if none is set yet — don't override an
      // active view (a parallel debate's session event may have set it).
      if (currentSessionId.value == null) {
        const saved = localStorage.getItem('chat_session_id')
        if (saved && sessions.value.find(s => s.id === parseInt(saved))) {
          currentSessionId.value = parseInt(saved)
        } else if (sessions.value.length > 0) {
          currentSessionId.value = sessions.value[0].id
        }
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
      messagesBySession.value[res.data.id] = []
      return res.data.id
    } catch (e) {
      console.error('createSession failed', e)
      return null
    }
  }

  async function selectSession(id: number) {
    currentSessionId.value = id
    localStorage.setItem('chat_session_id', String(id))
    // ISSUE-030 fix: do NOT refetch+overwrite a buffer that's actively
    // streaming — the live _streamDebate holds the buffer reference and keeps
    // filling it; refetching would replace it with stale persisted data (only
    // committed messages, not in-flight tokens) AND orphan the live buf ref so
    // subsequent tokens vanish. The live buffer IS the source of truth while
    // streaming.
    if (streamingSessions.value[id]) return
    try {
      const res = await apiClient.get(`/chat/sessions/${id}`)
      if (res.data && !res.data.error) {
        messagesBySession.value[id] = (res.data.messages || []).map((m: any) => ({
          ...m, reasoning: m.meta?.reasoning || m.reasoning,
        }))
      }
    } catch (e) {
      console.error('selectSession failed', e)
    }
  }

  async function deleteSession(id: number) {
    try {
      await apiClient.delete(`/chat/sessions/${id}`)
      sessions.value = sessions.value.filter(s => s.id !== id)
      delete messagesBySession.value[id]
      if (currentSessionId.value === id) {
        currentSessionId.value = sessions.value.length > 0 ? sessions.value[0].id : null
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
      removed.forEach((id) => delete messagesBySession.value[id])
      if (currentSessionId.value !== null && removed.has(currentSessionId.value)) {
        currentSessionId.value = sessions.value.length > 0 ? sessions.value[0].id : null
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
    const buf = bufOf(sessionId)
    buf.push({ role: 'user', content: text })

    const ac = new AbortController()
    abortControllers.set(sessionId, ac)
    streamingSessions.value[sessionId] = true

    try {
      const token = sessionStorage.getItem('token')
      const res = await fetch(`/api/v1/chat/sessions/${sessionId}/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ message: text, agent_ids: agentIds }),
        signal: ac.signal,
      })
      if (!res.ok) {
        handleStreamAuthFailure(res.status)
        throw new Error(`HTTP ${res.status}`)
      }
      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let sseBuf = ''

      // 多 agent @mention（≥2）→ 事件流为 agent_start/token/done/search_*；
      // 单 agent → text 事件
      if (agentIds.length >= 2) {
        const agentIdx = new Map<number, number>()
        let searchIdx = -1
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          sseBuf += decoder.decode(value, { stream: true })
          let idx
          while ((idx = sseBuf.indexOf('\n\n')) >= 0) {
            const block = sseBuf.slice(0, idx); sseBuf = sseBuf.slice(idx + 2)
            const lines = block.split('\n')
            const ev = lines[0]?.replace('event: ', '') || ''
            const dataStr = lines[1]?.replace('data: ', '') || '{}'
            try {
              const data = JSON.parse(dataStr)
              if (ev === 'factbook_start') {
                let si = buf.findIndex(m => m.meta?.round_type === 'factbook')
                if (si < 0) { buf.push({ role: 'system', content: '', streaming: true, meta: { round_type: 'factbook' } }); si = buf.length - 1 }
                searchIdx = si
              } else if (ev === 'factbook_reasoning') {
                if (searchIdx >= 0) buf[searchIdx].reasoning = (buf[searchIdx].reasoning || '') + data.delta
              } else if (ev === 'factbook_token') {
                if (searchIdx >= 0) buf[searchIdx].content += data.delta
              } else if (ev === 'factbook_done') {
                if (searchIdx >= 0) { buf[searchIdx].content = data.content; if (data.reasoning) buf[searchIdx].reasoning = data.reasoning; buf[searchIdx].streaming = false }
              } else if (ev === 'agent_start') {
                buf.push({ role: 'assistant', content: '', streaming: true, agents_used: [data.agent_name],
                  meta: { round_type: data.round_type || 'analysis', agent_id: data.agent_id, agent_name: data.agent_name, round_num: data.round_num || 1 } })
                agentIdx.set(data.agent_id, buf.length - 1)
              } else if (ev === 'agent_reasoning') {
                const i = agentIdx.get(data.agent_id); if (i != null) buf[i].reasoning = (buf[i].reasoning || '') + data.delta
              } else if (ev === 'agent_token') {
                const i = agentIdx.get(data.agent_id); if (i != null) buf[i].content += data.delta
              } else if (ev === 'agent_done') {
                const i = agentIdx.get(data.agent_id)
                if (i != null) { if (data.content) buf[i].content = data.content; if (data.reasoning) buf[i].reasoning = data.reasoning; buf[i].streaming = false }
              } else if (ev === 'error') {
                buf.push({ role: 'system', content: `⚠️ ${data.message || '出错'}`, meta: { round_type: 'error' } })
              }
            } catch (e) { console.error('SSE parse error', e) }
          }
        }
      } else {
        // 单 agent → text 事件（用 buf[idx] 而非局部变量，确保 Vue 响应式）
        buf.push({ role: 'assistant' as const, content: '', streaming: true })
        const aiIdx = buf.length - 1
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          sseBuf += decoder.decode(value, { stream: true })
          let idx
          while ((idx = sseBuf.indexOf('\n\n')) >= 0) {
            const block = sseBuf.slice(0, idx); sseBuf = sseBuf.slice(idx + 2)
            const lines = block.split('\n')
            const eventType = lines[0]?.replace('event: ', '') || ''
            const dataStr = lines[1]?.replace('data: ', '') || '{}'
            try {
              const data = JSON.parse(dataStr)
              if (eventType === 'text' && data.content) {
                buf[aiIdx].content += data.content
              } else if (eventType === 'reasoning' && data.delta) {
                buf[aiIdx].reasoning = (buf[aiIdx].reasoning || '') + data.delta
              } else if (eventType === 'stop') {
                buf[aiIdx].streaming = false
              } else if (eventType === 'error') {
                buf[aiIdx].content += `\n\n⚠️ ${data.message}`
                buf[aiIdx].streaming = false
                buf[aiIdx].error = true
              }
            } catch (e) { console.error('SSE parse error', e) }
          }
        }
        buf[aiIdx].streaming = false
        // 自动生成标题
        const session = sessions.value.find(s => s.id === sessionId)
        if (session && session.title === '新对话') {
          session.title = text.slice(0, 20) + (text.length > 20 ? '…' : '')
        }
      }
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        buf.push({ role: 'system', content: `⚠️ ${e.message}`, meta: { round_type: 'error' } })
      }
    } finally {
      streamingSessions.value[sessionId] = false
      abortControllers.delete(sessionId)
      await loadSessions()
    }
  }

  // 直播辩论：在 chat 会话里流式渲染多 agent 气泡。agent 失败发 agent_failed 后
  // 后端暂停（不发 done），前端把该气泡标 error + 显示原地重试按钮；点重试调
  // resumeDebate 从失败处继续（已完成的 agent 跳过）。
  async function startDebate(agentIds: number[], targetCode: string, targetName: string, rounds: number, validateData: boolean = false) {
    // 不清 messages——辩论用新会话，session 事件会切到新空 buffer；清当前会话 buffer 会丢别的对话
    const ac = new AbortController()
    try {
      const token = sessionStorage.getItem('token')
      const res = await fetch('/api/v1/debate/start-stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ agent_ids: agentIds, target_type: 'stock', target_id: targetCode, rounds, validate_data: validateData }),
        signal: ac.signal,
      })
      if (!res.ok) {
        handleStreamAuthFailure(res.status)
        throw new Error(`HTTP ${res.status}`)
      }
      // Per-session streaming flag + controller are registered inside
      // _streamDebate when the `session` event arrives (sid unknown until
      // then). Cleared in _streamDebate's finally.
      await _streamDebate(res, { agentIds, targetName, targetCode, abortController: ac })
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        messages.value.push({ role: 'system', content: `⚠️ 辩论失败：${e.message}`, meta: { round_type: 'error' } })
      }
    } finally {
      await loadSessions()
    }
  }

  // 原地重试：从失败的 agent 处继续。resume 模式下 agent_start 会重置已有失败气泡。
  async function resumeDebate() {
    if (!currentSessionId.value) return
    const sessionId = currentSessionId.value
    const ac = new AbortController()
    abortControllers.set(sessionId, ac)
    streamingSessions.value[sessionId] = true
    try {
      const token = sessionStorage.getItem('token')
      const res = await fetch(`/api/v1/debate/sessions/${sessionId}/resume-stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        signal: ac.signal,
      })
      if (!res.ok) {
        handleStreamAuthFailure(res.status)
        throw new Error(`HTTP ${res.status}`)
      }
      await _streamDebate(res, { isResume: true, abortController: ac })
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        messages.value.push({ role: 'system', content: `⚠️ 重试失败：${e.message}`, meta: { round_type: 'error' } })
      }
    } finally {
      streamingSessions.value[sessionId] = false
      abortControllers.delete(sessionId)
      await loadSessions()
    }
  }

  // 共享 SSE 驱动：处理 start/resume 两路事件流。agent_failed/summary_failed → 暂停。
  async function _streamDebate(res: Response, opts: { isResume?: boolean, agentIds?: number[], targetName?: string, targetCode?: string, abortController?: AbortController } = {}) {
    const isResume = !!opts.isResume
    const agentMsgIdx = new Map<string, number>()
    let summaryIdx = -1
    let factbookIdx = -1
    let validationIdx = -1
    let sessionId: number | null = null
    // buf = 辩论会话自己的消息缓冲（不随用户切会话变化）。流式只写 buf，
    // 可见 messages（computed）= currentSessionId 的缓冲——用户切走时 buf 继续后台填充，
    // 切回来自动显示已填充的 buf，不串到别的会话气泡。
    let buf: ChatMessageData[] = []
    const reader = res.body!.getReader()
    const decoder = new TextDecoder()
    let sseBuffer = ''
    let stopped = false
    try {
      while (!stopped) {
      const { done, value } = await reader.read()
      if (done) break
      sseBuffer += decoder.decode(value, { stream: true })
      let idx
      while ((idx = sseBuffer.indexOf('\n\n')) >= 0) {
        const block = sseBuffer.slice(0, idx)
        sseBuffer = sseBuffer.slice(idx + 2)
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
            // Register per-session streaming flag + controller (ISSUE-030 fix)
            // so selectSession skips refetching this buffer while it streams.
            streamingSessions.value[sid] = true
            if (opts.abortController) abortControllers.set(sid, opts.abortController)
            buf = bufOf(sid)
            if (!isResume) buf.length = 0  // fresh 辩论：清空；resume：保留已有气泡
            if (!isResume && !sessions.value.find(s => s.id === sid)) {
              sessions.value.unshift({
                id: sid, title: `辩论：${opts.targetName}(${opts.targetCode})`,
                agent_ids: opts.agentIds || [], type: 'debate', pinned: false,
              })
            }
          } else if (ev === 'collecting') {
            // FactBook 采集进度（正在获取价值分析/K线/行业/宏观/市场状态…）
            let ci = buf.findIndex(m => m.meta?.round_type === 'collecting')
            if (ci < 0) {
              buf.push({ role: 'system', content: data.message, meta: { round_type: 'collecting', stage: data.stage } })
            } else {
              buf[ci].content = data.message
              buf[ci].meta = { round_type: 'collecting', stage: data.stage }
            }
          } else if (ev === 'factbook_start' || ev === 'factbook') {
            // 事实 agent 占位 system 气泡（写到 buf，不是 messages.value）
            let fbIdx = buf.findIndex(m => m.meta?.round_type === 'factbook')
            if (fbIdx < 0) {
              buf.push({ role: 'system', content: '', streaming: true, meta: { round_type: 'factbook' } })
              fbIdx = buf.length - 1
              factbookIdx = fbIdx
            } else {
              buf[fbIdx].content = ''; buf[fbIdx].streaming = true; buf[fbIdx].error = false
              factbookIdx = fbIdx
            }
            if (ev === 'factbook') { buf[fbIdx].content = data.content; buf[fbIdx].streaming = false }
          } else if (ev === 'factbook_token') {
            if (factbookIdx >= 0) buf[factbookIdx].content += data.delta
          } else if (ev === 'factbook_done') {
            if (factbookIdx >= 0) { buf[factbookIdx].content = data.content; buf[factbookIdx].streaming = false }
          } else if (ev === 'validation_start') {
            let vi = buf.findIndex(m => m.meta?.round_type === 'validation')
            if (vi < 0) { buf.push({ role: 'system', content: '', streaming: true, meta: { round_type: 'validation' } }); vi = buf.length - 1 }
            validationIdx = vi
          } else if (ev === 'validation_reasoning') {
            if (validationIdx >= 0) buf[validationIdx].reasoning = (buf[validationIdx].reasoning || '') + data.delta
          } else if (ev === 'validation_token') {
            if (validationIdx >= 0) buf[validationIdx].content += data.delta
          } else if (ev === 'validation_done') {
            if (validationIdx >= 0) { buf[validationIdx].content = data.content; if (data.reasoning) buf[validationIdx].reasoning = data.reasoning; buf[validationIdx].streaming = false }
          } else if (ev === 'agent_start') {
            const key = `${data.round_num}:${data.agent_id}`
            const existIdx = isResume
              ? buf.findIndex(m => m.meta?.round_num === data.round_num && m.meta?.agent_id === data.agent_id && m.meta?.round_type === data.round_type)
              : -1
            if (existIdx >= 0) {
              buf[existIdx].content = ''
              buf[existIdx].streaming = true
              buf[existIdx].error = false
              agentMsgIdx.set(key, existIdx)
            } else {
              buf.push({
                role: 'assistant', content: '', streaming: true,
                agents_used: [data.agent_name],
                meta: { round_type: data.round_type, round_num: data.round_num, agent_id: data.agent_id, agent_name: data.agent_name },
              })
              agentMsgIdx.set(key, buf.length - 1)
            }
          } else if (ev === 'agent_token') {
            const i = agentMsgIdx.get(`${data.round_num}:${data.agent_id}`)
            if (i != null) buf[i].content += data.delta
          } else if (ev === 'agent_reasoning') {
            const i = agentMsgIdx.get(`${data.round_num}:${data.agent_id}`)
            if (i != null) buf[i].reasoning = (buf[i].reasoning || '') + data.delta
          } else if (ev === 'agent_done') {
            const i = agentMsgIdx.get(`${data.round_num}:${data.agent_id}`)
            if (i != null) {
              buf[i].content = data.content
              if (data.reasoning) buf[i].reasoning = data.reasoning
              buf[i].streaming = false
            }
          } else if (ev === 'agent_failed') {
            const i = agentMsgIdx.get(`${data.round_num}:${data.agent_id}`)
            if (i != null) {
              buf[i].streaming = false
              buf[i].error = true
              buf[i].meta = { ...(buf[i].meta || {}), error: data.error }
            }
            stopped = true  // 暂停，等前端重试
          } else if (ev === 'summary_start') {
            let si = buf.findIndex(m => m.meta?.round_type === 'summary')
            if (si < 0) {
              buf.push({ role: 'assistant', content: '', streaming: true, agents_used: ['总结'], meta: { round_type: 'summary' } })
              si = buf.length - 1
            } else {
              buf[si].content = ''; buf[si].reasoning = ''; buf[si].streaming = true; buf[si].error = false
            }
            summaryIdx = si
          } else if (ev === 'summary_reasoning') {
            if (summaryIdx >= 0) buf[summaryIdx].reasoning = (buf[summaryIdx].reasoning || '') + data.delta
          } else if (ev === 'summary_token') {
            if (summaryIdx >= 0) buf[summaryIdx].content += data.delta
          } else if (ev === 'summary_done') {
            if (summaryIdx >= 0) {
              buf[summaryIdx].content = data.content
              if (data.reasoning) buf[summaryIdx].reasoning = data.reasoning
              buf[summaryIdx].streaming = false
            }
          } else if (ev === 'summary_failed') {
            if (summaryIdx >= 0) { buf[summaryIdx].streaming = false; buf[summaryIdx].error = true }
            stopped = true
          } else if (ev === 'error') {
            buf.push({ role: 'system', content: `⚠️ ${data.message || '辩论出错'}`, meta: { round_type: 'error' } })
          }
        } catch (e) {
          console.error('Debate SSE parse error', e)
        }
      }
    }
    } finally {
      // Clear this session's streaming flag so future selectSession can refetch
      // (the stream is done; the buffer is now the persisted truth via
      // loadSessions/selectSession). ISSUE-030 fix.
      if (sessionId != null) {
        streamingSessions.value[sessionId] = false
        abortControllers.delete(sessionId)
      }
    }
    return sessionId
  }

  async function retryLastMessage(agentIds: number[] = []) {
    // 操作当前会话的缓冲（非辩论会话的重试）
    const sid = currentSessionId.value
    if (sid == null) return
    const buf = bufOf(sid)
    const lastUserIdx = [...buf].reverse().findIndex(m => m.role === 'user')
    if (lastUserIdx < 0) return
    const lastUser = buf[buf.length - 1 - lastUserIdx]
    // Remove everything after the last user message (failed assistant reply)
    messagesBySession.value[sid] = buf.slice(0, buf.length - lastUserIdx)
    // Resend
    await sendMessage(lastUser.content, agentIds)
  }

  function stopStreaming() {
    // Abort the CURRENT session's stream (ISSUE-030: per-session controllers).
    const sid = currentSessionId.value
    if (sid != null) {
      abortControllers.get(sid)?.abort()
    }
  }

  return {
    sessions, currentSessionId, currentSession, messages, streaming,
    currentSessionStreaming,
    loadSessions, createSession, selectSession, deleteSession, deleteSessions, renameSession,
    sendMessage, startDebate, resumeDebate, stopStreaming, retryLastMessage,
  }
})
