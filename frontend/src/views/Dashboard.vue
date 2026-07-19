<template>
  <n-space vertical size="large">
    <n-grid :cols="4" :x-gap="16">
      <n-gi>
        <n-statistic label="股票总数" :value="stats.stockCount" />
      </n-gi>
      <n-gi>
        <n-statistic label="投资组合" :value="stats.portfolioCount" />
      </n-gi>
      <n-gi>
        <n-statistic label="筛选脚本" :value="stats.filterCount" />
      </n-gi>
      <n-gi>
        <n-statistic label="投资Agent" :value="stats.agentCount" />
      </n-gi>
    </n-grid>

    <n-grid :cols="2" :x-gap="16">
      <n-gi>
        <n-card title="快速操作">
          <n-space>
            <n-button @click="$router.push('/stocks')">查看股票</n-button>
            <n-button @click="$router.push('/filters')">创建筛选</n-button>
            <n-button @click="$router.push('/backtest')">策略回测</n-button>
            <n-button @click="$router.push('/debate')">辩论分析</n-button>
          </n-space>
        </n-card>
      </n-gi>
      <n-gi>
        <n-card title="数据采集">
          <n-space vertical>
            <n-button @click="startCollection('full')" :loading="collecting" :disabled="!!taskStore.activeTaskId">全量采集基础指标</n-button>
            <n-button @click="startCollection('incremental')" :loading="collecting" :disabled="!!taskStore.activeTaskId">增量更新</n-button>
            <n-button @click="startCollection('financial')" :loading="collecting" :disabled="!!taskStore.activeTaskId">全量更新财务数据</n-button>
          </n-space>
        </n-card>
      </n-gi>
    </n-grid>

    <!-- Task Progress -->
    <TaskProgress
      v-if="taskStore.activeTaskId"
      :task-id="taskStore.activeTaskId"
      :show-controls="true"
      @completed="onTaskCompleted"
      @failed="onTaskFailed"
      @stopped="onTaskStopped"
    />

    <n-card title="最近通知">
      <n-list v-if="notifications.length">
        <n-list-item v-for="n in notifications.slice(0, 5)" :key="n.id">
          <n-thing :title="n.title" :description="n.content" />
        </n-list-item>
      </n-list>
      <n-empty v-else description="暂无通知" />
    </n-card>
  </n-space>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useMessage } from 'naive-ui'
import { stocksApi, portfoliosApi, filtersApi, agentsApi, dataApi, notificationsApi, tasksApi } from '../api'
import { useTaskStore } from '../stores/taskStore'
import TaskProgress from '../components/common/TaskProgress.vue'

const message = useMessage()
const taskStore = useTaskStore()
const stats = ref({ stockCount: 0, portfolioCount: 0, filterCount: 0, agentCount: 0 })
const notifications = ref<any[]>([])
const collecting = ref(false)

onMounted(async () => {
  try {
    const [stocks, portfolios, filters, agents, notifs] = await Promise.all([
      stocksApi.list({ limit: 1 }),
      portfoliosApi.list(),
      filtersApi.list(),
      agentsApi.list(),
      notificationsApi.list(),
    ])
    stats.value = {
      stockCount: stocks.data.length,
      portfolioCount: portfolios.data.length,
      filterCount: filters.data.length,
      agentCount: agents.data.length,
    }
    notifications.value = notifs.data
  } catch (e) {
    console.error('Failed to load dashboard data:', e)
  }

  // Restore running tasks from backend
  if (!taskStore.activeTaskId) {
    try {
      const res = await tasksApi.list()
      const runningTask = res.data.find((t: any) =>
        t.status === 'running' || t.status === 'paused' || t.status === 'pending'
      )
      if (runningTask) {
        taskStore.setActiveTask(runningTask.task_id)
        message.info(`恢复任务: ${runningTask.task_type}`)
      }
    } catch (e) {
      console.error('Failed to check running tasks:', e)
    }
  }
})

async function startCollection(type: string) {
  collecting.value = true
  try {
    let res
    if (type === 'full') {
      res = await dataApi.startFullCollection()
    } else if (type === 'incremental') {
      res = await dataApi.startIncrementalUpdate()
    } else if (type === 'financial') {
      res = await dataApi.startFinancialUpdate()
    }
    const taskId = res.data.task_id
    if (taskId) {
      taskStore.setActiveTask(taskId)
      message.success('数据采集任务已启动')
    } else {
      message.warning('任务已启动但未返回任务ID')
    }
  } catch (e: any) {
    message.error('启动失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    collecting.value = false
  }
}

function onTaskCompleted() {
  message.success('数据采集完成')
  taskStore.clearActiveTask()
  refreshStats()
}

function onTaskFailed() {
  message.error('数据采集失败')
  taskStore.clearActiveTask()
}

function onTaskStopped() {
  message.warning('数据采集已停止')
  taskStore.clearActiveTask()
}

async function refreshStats() {
  try {
    const [stocks, portfolios, filters, agents] = await Promise.all([
      stocksApi.list({ limit: 1 }),
      portfoliosApi.list(),
      filtersApi.list(),
      agentsApi.list(),
    ])
    stats.value = {
      stockCount: stocks.data.length,
      portfolioCount: portfolios.data.length,
      filterCount: filters.data.length,
      agentCount: agents.data.length,
    }
  } catch (e) {
    console.error('Failed to refresh stats:', e)
  }
}
</script>
