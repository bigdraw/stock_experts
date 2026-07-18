<template>
  <n-card v-if="task" :title="taskTitle" size="small">
    <template #header-extra>
      <n-tag :type="statusType" size="small">{{ statusText }}</n-tag>
    </template>

    <n-space vertical>
      <!-- Progress Bar -->
      <n-progress
        type="line"
        :percentage="task.progress"
        :status="progressStatus"
        :show-indicator="true"
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
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useMessage } from 'naive-ui'
import { tasksApi } from '../../api'

interface TaskProgress {
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
const task = ref<TaskProgress | null>(null)
const loading = ref(false)
let eventSource: EventSource | null = null

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

async function fetchTask() {
  try {
    const res = await tasksApi.get(props.taskId)
    task.value = res.data
  } catch (e) {
    console.error('Failed to fetch task:', e)
  }
}

function connectSSE() {
  const token = localStorage.getItem('token')
  const url = `/api/v1/tasks/${props.taskId}/stream?token=${token}`
  
  eventSource = new EventSource(url)
  
  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      task.value = data
      
      // Emit events for terminal states
      if (data.status === 'completed') {
        emit('completed')
        closeSSE()
      } else if (data.status === 'failed') {
        emit('failed')
        closeSSE()
      } else if (data.status === 'stopped') {
        emit('stopped')
        closeSSE()
      }
    } catch (e) {
      console.error('Failed to parse SSE data:', e)
    }
  }
  
  eventSource.onerror = () => {
    console.error('SSE connection error')
    closeSSE()
  }
}

function closeSSE() {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
}

async function pauseTask() {
  loading.value = true
  try {
    await tasksApi.pause(props.taskId)
    message.success('任务已暂停')
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
  } catch (e: any) {
    message.error(e.response?.data?.detail || '停止失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchTask()
  connectSSE()
})

onUnmounted(() => {
  closeSSE()
})
</script>
