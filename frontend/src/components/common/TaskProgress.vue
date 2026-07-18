<template>
  <n-card v-if="task" :title="taskTitle" size="small">
    <template #header-extra>
      <n-space align="center" :size="8">
        <n-tag :type="statusType" size="small">{{ statusText }}</n-tag>
        <n-tag v-if="connectionStatus !== 'connected'" type="warning" size="tiny">
          {{ connectionStatus === 'connecting' ? '连接中...' : '轮询模式' }}
        </n-tag>
      </n-space>
    </template>

    <n-space vertical>
      <!-- Progress Bar -->
      <n-progress
        type="line"
        :percentage="task.progress"
        :status="progressStatus"
        :show-indicator="true"
        :processing="task.status === 'running'"
      />

      <!-- Progress Details -->
      <n-space justify="space-between">
        <n-text depth="3">{{ task.message }}</n-text>
        <n-text depth="3" v-if="task.total > 0">
          {{ task.current }} / {{ task.total }}
        </n-text>
      </n-space>

      <!-- Control Buttons -->
      <n-space v-if="showControls">
        <n-button
          v-if="task.status === 'running'"
          size="small"
          @click="pauseTask"
          :loading="loading"
        >
          暂停
        </n-button>
        <n-button
          v-if="task.status === 'paused'"
          size="small"
          type="primary"
          @click="resumeTask"
          :loading="loading"
        >
          继续
        </n-button>
        <n-button
          v-if="task.status === 'running' || task.status === 'paused'"
          size="small"
          type="error"
          @click="stopTask"
          :loading="loading"
        >
          停止
        </n-button>
      </n-space>

      <!-- Error Message -->
      <n-alert v-if="task.error" type="error" :title="task.error" />
    </n-space>
  </n-card>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { tasksApi } from '../../api'

interface TaskData {
  task_id: string
  task_type: string
  status: string
  progress: number
  current: number
  total: number
  message: string
  started_at?: string
  completed_at?: string
  error?: string
  metadata?: Record<string, any>
}

const props = defineProps<{
  taskId: string
  showControls?: boolean
}>()

const emit = defineEmits<{
  (e: 'completed'): void
  (e: 'failed'): void
  (e: 'stopped'): void
}>()

const message = useMessage()
const task = ref<TaskData | null>(null)
const loading = ref(false)
const connectionStatus = ref<'connecting' | 'connected' | 'polling'>('connecting')

let eventSource: EventSource | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null
let sseRetryCount = 0
const MAX_SSE_RETRIES = 3

const taskTitle = computed(() => {
  const typeMap: Record<string, string> = {
    full_basic: '全量数据采集',
    incremental: '增量更新',
    deep: '深度数据获取',
    backtest: '策略回测',
    book_analysis: '书籍分析',
  }
  return typeMap[task.value?.task_type || ''] || '任务进度'
})

const statusType = computed(() => {
  const statusMap: Record<string, 'default' | 'info' | 'success' | 'warning' | 'error'> = {
    pending: 'default',
    running: 'info',
    paused: 'warning',
    completed: 'success',
    failed: 'error',
    stopped: 'warning',
  }
  return statusMap[task.value?.status || 'pending'] || 'default'
})

const statusText = computed(() => {
  const statusMap: Record<string, string> = {
    pending: '等待中',
    running: '运行中',
    paused: '已暂停',
    completed: '已完成',
    failed: '失败',
    stopped: '已停止',
  }
  return statusMap[task.value?.status || 'pending'] || '未知'
})

const progressStatus = computed(() => {
  if (task.value?.status === 'completed') return 'success'
  if (task.value?.status === 'failed') return 'error'
  return 'default'
})

function isTerminalStatus(status: string): boolean {
  return ['completed', 'failed', 'stopped'].includes(status)
}

async function fetchTask() {
  try {
    const res = await tasksApi.get(props.taskId)
    task.value = res.data
    if (isTerminalStatus(res.data.status)) {
      emitTerminalEvent(res.data.status)
      stopPolling()
    }
  } catch (e) {
    console.error('Failed to fetch task:', e)
  }
}

function emitTerminalEvent(status: string) {
  if (status === 'completed') emit('completed')
  else if (status === 'failed') emit('failed')
  else if (status === 'stopped') emit('stopped')
}

function connectSSE() {
  closeSSE()
  connectionStatus.value = 'connecting'

  const token = localStorage.getItem('token')
  const url = `/api/v1/tasks/${props.taskId}/stream?token=${token}`

  eventSource = new EventSource(url)

  eventSource.onopen = () => {
    connectionStatus.value = 'connected'
    sseRetryCount = 0
  }

  eventSource.onmessage = (event) => {
    try {
      // Skip heartbeat comments
      if (event.data.startsWith(':')) return

      const data = JSON.parse(event.data)
      task.value = data

      if (isTerminalStatus(data.status)) {
        emitTerminalEvent(data.status)
        closeSSE()
        stopPolling()
      }
    } catch (e) {
      console.error('Failed to parse SSE data:', e)
    }
  }

  eventSource.onerror = () => {
    sseRetryCount++
    if (sseRetryCount >= MAX_SSE_RETRIES) {
      console.warn('SSE failed after retries, falling back to polling')
      closeSSE()
      startPolling()
    } else {
      // EventSource auto-reconnects, but we track the retry count
      connectionStatus.value = 'connecting'
    }
  }
}

function closeSSE() {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
}

function startPolling() {
  stopPolling()
  connectionStatus.value = 'polling'
  // Poll every 2 seconds
  pollTimer = setInterval(async () => {
    await fetchTask()
    if (task.value && isTerminalStatus(task.value.status)) {
      stopPolling()
    }
  }, 2000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function pauseTask() {
  loading.value = true
  try {
    await tasksApi.pause(props.taskId)
    message.success('任务已暂停')
    await fetchTask()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '暂停失败')
  } finally {
    loading.value = false
  }
}

async function resumeTask() {
  loading.value = true
  try {
    await tasksApi.resume(props.taskId)
    message.success('任务已继续')
    await fetchTask()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '继续失败')
  } finally {
    loading.value = false
  }
}

async function stopTask() {
  loading.value = true
  try {
    await tasksApi.stop(props.taskId)
    message.success('任务已停止')
    await fetchTask()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '停止失败')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await fetchTask()
  if (task.value && !isTerminalStatus(task.value.status)) {
    connectSSE()
  }
})

onUnmounted(() => {
  closeSSE()
  stopPolling()
})
</script>
