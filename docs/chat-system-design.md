# 聊天系统设计文档（基于 LobeChat 架构，Vue3+FastAPI 自主实现）

> 深入研读 lobehub/lobe-chat (canary) 源码后，提取其架构精髓，转化为我们 Vue3+naive-ui+Pinia+FastAPI 栈的实现方案。
> 参考：`E:\aicode\lobe-chat-study`（本地 clone，canary 分支）。
> **不含 TTS/语音**（后续单独做）。

---

## 1. 数据模型（SQLAlchemy，简化 LobeChat 四层为两层）

LobeChat 用 Session→Topic→MessageGroup→Message 四层 + Thread。我们简化为 **ChatSession + ChatMessage 两层**，用 `is_compressed` 布尔 + `summary` 字段替代 MessageGroup 表。

### 1.1 ChatSession

```python
class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(100), default="新对话")
    agent_ids: Mapped[list] = mapped_column(JSON, default=list)  # @提及的 agent ID
    summary: Mapped[str | None] = mapped_column(Text)  # 上下文压缩后的摘要
    summary_upto_msg_id: Mapped[int | None] = mapped_column(Integer)  # 摘要到哪条消息为止
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at / updated_at / last_message_at  # 时间戳
```

### 1.2 ChatMessage

```python
class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = primary_key, autoincrement
    session_id: Mapped[int] = FK("chat_sessions.id"), index=True
    role: Mapped[str]  # user / assistant / system
    content: Mapped[str] = Text
    agents_used: Mapped[list] = JSON  # 哪些 agent 参与了
    stocks_detected: Mapped[list] = JSON  # 自动检测到的股票代码
    token_count: Mapped[int] = default(0)  # 粗略 token 估算
    is_compressed: Mapped[bool] = default(False)  # 被压缩收纳的旧消息
    created_at: Mapped[datetime]
```

**关键**：`is_compressed=True` 的消息不进入 LLM 上下文（等价 LobeChat 的 `messageGroupId IS NOT NULL`）。查询活跃消息：`WHERE is_compressed = False`。

### 1.3 与 LobeChat 的对应关系

| LobeChat | 我们 | 说明 |
|---|---|---|
| Session | ChatSession | 1:1，加 user_id |
| Topic | （省略） | 不需要 Topic 子层，Session 内直接管消息 |
| MessageGroup(type=compression) | `is_compressed` 布尔 + `summary` 字段 | 用字段替代独立表 |
| Message | ChatMessage | 1:1，加 agents_used/stocks_detected |
| Thread | （省略） | 不做消息分支树 |
| clientId 去重 | （省略） | 单用户不需要 |

---

## 2. 上下文压缩（移植 LobeChat 算法）

### 2.1 阈值判断（shouldCompress）

参考 LobeChat `tokenCounter.ts` + `tokenAccounting/index.ts`：

```python
DEFAULT_MAX_CONTEXT = 128_000    # 模型上下文窗口
DEFAULT_THRESHOLD_RATIO = 0.5   # 达到 50% 窗口就压缩
DEFAULT_DRIFT_MULTIPLIER = 1.25  # token 估算补偿

def should_compress(messages, max_context=128_000, ratio=0.5):
    raw_tokens = sum(len(m.content) // 4 for m in messages)  # 粗估：4 char ≈ 1 token
    adjusted = math.ceil(raw_tokens * 1.25)
    threshold = math.floor(max_context * ratio)  # 64_000
    return adjusted > threshold
```

**触发条件**：`ceil(rawTokens × 1.25) > maxContext × 0.5`，即原始 token 超过 ~51,200 时压缩。

### 2.2 压缩流程（移植 compressContext.ts 四步）

```
1. should_compress(messages) → True
2. 保留最近 N=4 条消息不压缩（preserved）
3. 取前 (total - 4) 条 → 调 LLM 生成摘要：
   prompt = "请总结以下对话的关键信息、决策、涉及的股票，保持简洁：\n" + old_messages
4. 事务：
   - 旧消息 is_compressed = True
   - session.summary = LLM 返回的摘要
   - session.summary_upto_msg_id = 最后一条被压缩的消息 ID
5. 下一轮 LLM 调用：
   system_prompt = agent_prompt + "\n[对话历史摘要]\n" + session.summary
   messages = [system, ...preserved_4_messages, new_user_message]
```

### 2.3 与 LobeChat 的差异

| LobeChat | 我们 | 理由 |
|---|---|---|
| MessageGroup 表 + createGroup/finalizeGroup 事务 | `is_compressed` 布尔 + `summary` 字段 | 不需要独立组表 |
| 流式摘要（边生成边写入 group content） | 一次性摘要（调 `llm.chat`） | 摘要本身不需要流式 |
| `compressionModel` 可单独配置 | 复用主 LLM | 简化 |
| group-aware HistoryTruncate（assistant+tool=1 unit） | 按"轮"截断（1 user + 1 assistant = 1 轮） | 我们没有 tool_calls 链 |

---

## 3. SSE 流式协议（移植 LobeChat chunk 格式）

### 3.1 Wire 格式

```
event: text\n
data: {"content": "增量文本"}\n\n

event: stop\n
data: {"reason": "stop"}\n\n

event: error\n
data: {"message": "错误信息"}\n\n
```

简化 LobeChat 的 13 种 chunk type 为 **3 种**：`text` / `stop` / `error`。省略 reasoning/tool_calls/grounding/base64_image/usage/speed 等（后续按需加）。

### 3.2 后端实现（FastAPI）

```python
@router.post("/chat/sessions/{session_id}/stream")
async def chat_stream(session_id: int, req: ChatStreamRequest, db, user):
    # 1. 加载会话 + 活跃消息（is_compressed=False）
    # 2. should_compress → 压缩
    # 3. 组装 system_prompt（agent prompt + summary）
    # 4. 股票代码自动取数（现有逻辑）
    # 5. 调 llm.chat_stream() 逐 chunk 返回

    async def event_stream():
        try:
            async for chunk in llm.chat_stream(messages):
                yield f"event: text\ndata: {json.dumps({'content': chunk.content})}\n\n"
            yield f"event: stop\ndata: {json.dumps({'reason': 'stop'})}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

**关键**：`X-Accel-Buffering: no` 防 nginx 缓冲（LobeChat 同款）。

### 3.3 前端流式渲染（fetch + ReadableStream）

不用 axios（不支持流式），用原生 `fetch`：

```ts
// composables/useChatStream.ts
async function streamMessage(sessionId: number, content: string, signal: AbortSignal) {
  const res = await fetch(`/api/v1/chat/sessions/${sessionId}/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ message: content, agent_ids: selectedAgentIds }),
    signal,
  })

  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    // 解析 SSE：按 \n\n 分割 event
    let idx
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      // 解析 event: xxx \n data: {...}
      const lines = block.split('\n')
      const eventType = lines[0]?.replace('event: ', '')
      const data = JSON.parse(lines[1]?.replace('data: ', '') || '{}')
      // 追加到 assistant 消息
      if (eventType === 'text') appendToMessage(data.content)
      if (eventType === 'stop') finalizeMessage()
      if (eventType === 'error') showError(data.message)
    }
  }
}
```

**停止生成**：`AbortController.abort()` → fetch 抛 AbortError → 已生成内容保留。

### 3.4 rAF 打字机（可选，参考 LobeChat createSmoothMessage）

LobeChat 的 `createSmoothMessage` 用 `requestAnimationFrame` 逐字符输出，积压越多越快。我们可以简化为**直接追加**（不做打字机效果），或用 `setInterval(50ms)` 批量 flush。打字机是锦上添花，不是必需。

---

## 4. System Prompt 管线（移植 LobeChat Provider 模式）

### 4.1 LobeChat 的 7 Phase 管线

LobeChat 用 `ContextEngine` 顺序执行 providers + processors，分 7 个 phase：
1. HistoryTruncate（截断）
2. System Message Assembly（SystemRoleInjector, ToolSystemRole, HistorySummary, SystemDate, ...）
3. Context Injection before first user（UserMemory, Knowledge, ToolDiscovery, ...）
4. User Message Augmentation（SelectedSkill, SelectedTool, ...）
5. Virtual Tail Guidance（prefix cache 友好）
6. Message Transformation（AgentCouncilFlatten, GroupFlatten, PlaceholderVariables, ...）
7. Content Processing + Cleanup

### 4.2 我们的简化版（4 个 Provider + 1 Processor）

```python
# backend/app/services/chat_pipeline.py

class ChatProvider(ABC):
    name: str
    inject_position: str  # "system" | "last_user"

    @abstractmethod
    async def build_content(self, ctx: dict) -> str | None: ...

class ChatProcessor(ABC):
    @abstractmethod
    async def process(self, messages: list[dict], ctx: dict) -> list[dict]: ...

# 实现：
class SystemRoleProvider(ChatProvider):
    """注入 agent 的 system_prompt（对应 LobeChat SystemRoleInjector）"""
    # 从 agent_ids 取 system_prompt 拼接

class HistorySummaryProvider(ChatProvider):
    """注入压缩摘要（对应 LobeChat HistorySummaryProvider）"""
    # session.summary 非空时注入 <chat_history_summary>...</chat_history_summary>

class StockDataProvider(ChatProvider):
    """注入股票数据（对应 LobeChat BaseLastUserContentProvider）"""
    # 检测 6 位股票代码 → 取 value_analysis → 包 <stock_data>...</stock_data>

class HistoryTruncateProcessor(ChatProcessor):
    """按轮截断（对应 LobeChat HistoryTruncateProcessor）"""
    # 保留最近 N 轮（1 user + 1 assistant = 1 轮）
```

**执行顺序**：
1. `HistoryTruncateProcessor.process(messages)` — 截断
2. `SystemRoleProvider.build_content()` → 追加到 system 消息
3. `HistorySummaryProvider.build_content()` → 追加到 system 消息
4. `StockDataProvider.build_content()` → 包 `<stock_data>` 追加到最后一条 user 消息

### 4.3 与现有 chat.py 的关系

现有 `chat.py` L39-84 的 `system_parts` 拼接 + 股票数据注入，**拆成上面的 4 个 Provider/Processor**。`chat.py` 端点变为：

```python
pipeline = ChatPipeline(providers=[SystemRoleProvider(), HistorySummaryProvider(), StockDataProvider()],
                        processors=[HistoryTruncateProcessor()])
messages = await pipeline.run(raw_messages, ctx)
# 流式调 LLM
async for chunk in llm.chat_stream(messages):
    yield SSE chunk
```

---

## 5. 前端架构（Vue3 + naive-ui + Pinia）

### 5.1 Pinia Store（`stores/chat.ts`）

```ts
export const useChatStore = defineStore('chat', () => {
  const sessions = ref<Session[]>([])
  const currentSessionId = ref<number | null>(null)
  const messages = ref<Message[]>([])
  const streaming = ref(false)
  let abortController: AbortController | null = null

  // 会话 CRUD
  async function loadSessions() { /* GET /chat/sessions */ }
  async function createSession(title?, agentIds?) { /* POST /chat/sessions */ }
  async function selectSession(id) { /* GET /chat/sessions/{id} → messages */ }
  async function deleteSession(id) { /* DELETE */ }
  async function renameSession(id, title) { /* PATCH */ }

  // 发消息（流式）
  async function sendMessage(text: string) {
    // 1. 先追加 user 消息到 UI（乐观更新）
    // 2. 创建 AbortController
    // 3. fetch SSE stream → 逐 chunk 追加到 assistant 消息
    // 4. 完成后持久化到后端
    // 5. 首次回复后自动生成标题
  }

  function stopStreaming() {
    abortController?.abort()
    streaming.value = false
  }

  return { sessions, currentSessionId, messages, streaming,
           loadSessions, createSession, selectSession, deleteSession, renameSession,
           sendMessage, stopStreaming }
})
```

**持久化**：sessions 列表从后端 DB 加载（真相源），`currentSessionId` 存 localStorage（刷新不丢）。messages 每次切会话从后端拉。

### 5.2 ChatHome.vue 布局（LobeChat 式三栏）

```
┌─────────────┬──────────────────────────────────┐
│  会话列表    │  消息区（markdown 渲染）           │
│  (侧边栏)    │                                   │
│             │  ┌─────────────────────────────┐  │
│  📌 新对话   │  │ user: 分析 600519           │  │
│  巴菲特分析  │  │ assistant: (markdown) ...   │  │
│  茅台估值    │  │ user: @格雷厄姆 再看看...   │  │
│  ...        │  │ assistant: (流式中...) ▋    │  │
│             │  └─────────────────────────────┘  │
│             │  ┌─────────────────────────────┐  │
│             │  │ @agent 标签 | 输入框 | 发送  │  │
│             │  │ 快捷按钮行                   │  │
│             │  └─────────────────────────────┘  │
└─────────────┴──────────────────────────────────┘
```

**侧边栏**：`n-layout-sider` + `n-list`（会话列表，可新建/删除/重命名/搜索）。
**消息区**：`n-card` + markdown 渲染（`markdown-it` + `highlight.js`）。
**输入栏**：保留现有 `@agent` dropdown + `/skills` dropdown + 快捷按钮 + 新增 Stop 按钮。

### 5.3 Markdown 渲染

新增依赖：`markdown-it` + `highlight.js`。

```vue
<template>
  <div class="markdown-body" v-html="renderedContent"></div>
</template>

<script setup>
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'

const md = new MarkdownIt({
  html: false,
  highlight: (str, lang) => {
    if (lang && hljs.getLanguage(lang)) {
      return `<pre class="hljs"><code>${hljs.highlight(str, { language: lang }).value}</code></pre>`
    }
    return `<pre class="hljs"><code>${md.utils.escapeHtml(str)}</code></pre>`
  }
})

const renderedContent = computed(() => md.render(props.content || ''))
</script>
```

代码块复制按钮：用 `@vueuse/core` 的 `useClipboard`，在 `<pre>` 上加一个 hover 显示的复制按钮。

### 5.4 流式消息渲染

```vue
<template>
  <div v-for="msg in messages" :key="msg.id" :class="msg.role">
    <MarkdownRenderer v-if="msg.content" :content="msg.content" />
    <n-spin v-if="msg.streaming" size="small" />
  </div>
</template>
```

流式时：`streaming=true` 的 assistant 消息末尾显示光标 `▋`，每收到一个 text chunk 追加到 `msg.content`，Vue 响应式更新 markdown 渲染。

---

## 6. API 端点清单

| Method | Path | 功能 |
|---|---|---|
| GET | `/chat/sessions` | 列出当前用户的会话 |
| POST | `/chat/sessions` | 创建新会话（title? + agent_ids?） |
| GET | `/chat/sessions/{id}` | 取会话 + 活跃 messages |
| PATCH | `/chat/sessions/{id}` | 重命名 |
| DELETE | `/chat/sessions/{id}` | 删除 |
| POST | `/chat/sessions/{id}/stream` | **流式发消息（SSE）** |
| POST | `/chat/sessions/{id}/compress` | 手动触发压缩 |
| GET | `/chat/agents` | 列出 agent（已有） |
| GET | `/chat/skills` | 列出技能（已有） |
| POST | `/chat/analyze/stock` | 个股分析（已有） |
| POST | `/chat/analyze/portfolio` | 组合分析（已有） |
| POST | `/chat/analyze/fund` | 基金分析（已有） |

---

## 7. 新增依赖

### 后端
- 无新依赖（SQLAlchemy + FastAPI StreamingResponse 已有）

### 前端
- `markdown-it` — markdown 渲染
- `highlight.js` — 代码语法高亮
- `@vueuse/core` — useClipboard（复制按钮）

---

## 8. 关键文件清单

| 文件 | 动作 |
|---|---|
| `backend/app/models/chat.py` | **新建**：ChatSession + ChatMessage 模型 |
| `backend/app/services/chat_pipeline.py` | **新建**：Provider/Processor 管线 |
| `backend/app/api/v1/chat.py` | **重写**：加 session CRUD + stream SSE + 压缩 + 管线 |
| `frontend/src/stores/chat.ts` | **新建**：Pinia chat store（多会话+流式） |
| `frontend/src/composables/useChatStream.ts` | **新建**：fetch+ReadableStream SSE 解析 |
| `frontend/src/components/chat/MarkdownRenderer.vue` | **新建**：markdown+代码高亮+复制 |
| `frontend/src/components/chat/SessionSidebar.vue` | **新建**：会话列表侧边栏 |
| `frontend/src/views/ChatHome.vue` | **重写**：三栏布局+流式+markdown |
| `frontend/src/api/chat.ts` | **新建**：chatApi（session CRUD + stream helper） |
| `frontend/src/router/index.ts` | **修改**：加 `/chat/:sessionId` 路由 |
| `frontend/package.json` | **修改**：加 markdown-it + highlight.js + @vueuse/core |

---

## 9. 实施顺序

1. **后端 Phase 1**：ChatSession + ChatMessage 模型 + session CRUD 端点
2. **后端 Phase 2**：chat_pipeline.py（4 个 Provider/Processor）+ stream SSE 端点 + 压缩
3. **前端 Phase 3**：install deps + chat store + useChatStream composable
4. **前端 Phase 4**：MarkdownRenderer + SessionSidebar 组件
5. **前端 Phase 5**：ChatHome.vue 重写（三栏布局+流式+markdown+停止）
6. **测试**：session CRUD + stream + 压缩 + 多会话切换 + @agent + 股票自动取数

---

## 10. 验证方式

1. `uv run python -m tests.test_chat` — session CRUD + stream + 压缩
2. `npx vue-tsc --noEmit && npx vite build`
3. 端到端：新建会话 → @巴菲特 分析 600519 → 看流式输出 → 切到另一会话 → 回来消息还在 → 发 20+ 条触发压缩 → 确认摘要生效 → Stop 按钮中断流式
