<template>
  <div class="dashboard-container">
    <!-- 统计卡片区域 -->
    <div class="stats-grid">
      <div class="stat-card stat-card-primary">
        <div class="stat-icon">
          <n-icon :size="32" color="#00d4aa">
            <TrendingUpOutline />
          </n-icon>
        </div>
        <div class="stat-content">
          <div class="stat-label">股票总数</div>
          <div class="stat-value">{{ stats.stockCount }}</div>
        </div>
      </div>

      <div class="stat-card stat-card-info">
        <div class="stat-icon">
          <n-icon :size="32" color="#6366f1">
            <BriefcaseOutline />
          </n-icon>
        </div>
        <div class="stat-content">
          <div class="stat-label">投资组合</div>
          <div class="stat-value">{{ stats.portfolioCount }}</div>
        </div>
      </div>

      <div class="stat-card stat-card-success">
        <div class="stat-icon">
          <n-icon :size="32" color="#10b981">
            <FunnelOutline />
          </n-icon>
        </div>
        <div class="stat-content">
          <div class="stat-label">筛选脚本</div>
          <div class="stat-value">{{ stats.filterCount }}</div>
        </div>
      </div>

      <div class="stat-card stat-card-warning">
        <div class="stat-icon">
          <n-icon :size="32" color="#f59e0b">
            <ChatbubblesOutline />
          </n-icon>
        </div>
        <div class="stat-content">
          <div class="stat-label">投资Agent</div>
          <div class="stat-value">{{ stats.agentCount }}</div>
        </div>
      </div>
    </div>

    <!-- 快速操作和数据采集 -->
    <div class="action-grid">
      <n-card title="快速操作" class="action-card">
        <template #header-extra>
          <n-icon :size="20" color="#6366f1">
            <FlashOutline />
          </n-icon>
        </template>
        <div class="quick-actions">
          <n-button 
            v-for="action in quickActions" 
            :key="action.key"
            @click="$router.push(action.route)"
            class="action-button"
            :style="{ '--action-color': action.color }"
          >
            <template #icon>
              <n-icon :size="18">
                <component :is="action.icon" />
              </n-icon>
            </template>
            {{ action.label }}
          </n-button>
        </div>
      </n-card>

      <n-card title="数据采集" class="action-card">
        <template #header-extra>
          <n-icon :size="20" color="#00d4aa">
            <CloudDownloadOutline />
          </n-icon>
        </template>
        <div class="collection-actions">
          <n-button 
            v-for="action in collectionActions" 
            :key="action.key"
            @click="startCollection(action.key)"
            :loading="collecting && collectingType === action.key"
            :disabled="!!taskStore.activeTaskId"
            class="collection-button"
            :style="{ '--action-color': action.color }"
          >
            <template #icon>
              <n-icon :size="18">
                <component :is="action.icon" />
              </n-icon>
            </template>
            {{ action.label }}
          </n-button>
        </div>
      </n-card>
    </div>

    <!-- 任务进度 -->
    <div v-if="taskStore.activeTaskId" class="task-progress-container">
      <TaskProgress
        :task-id="taskStore.activeTaskId"
        :show-controls="true"
        @completed="onTaskCompleted"
        @failed="onTaskFailed"
        @stopped="onTaskStopped"
      />
    </div>

    <!-- 最近通知 -->
    <n-card title="最近通知" class="notification-card">
      <template #header-extra>
        <n-icon :size="20" color="#f59e0b">
          <NotificationsOutline />
        </n-icon>
      </template>
      <n-list v-if="notifications.length" class="notification-list">
        <n-list-item v-for="n in notifications.slice(0, 5)" :key="n.id" class="notification-item">
          <n-thing>
            <template #header>
              <span class="notification-title">{{ n.title }}</span>
            </template>
            <template #description>
              <span class="notification-content">{{ n.content }}</span>
            </template>
          </n-thing>
        </n-list-item>
      </n-list>
      <n-empty v-else description="暂无通知" />
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, h } from 'vue'
import { useMessage } from 'naive-ui'
import { 
  TrendingUpOutline, 
  BriefcaseOutline, 
  FunnelOutline, 
  ChatbubblesOutline,
  FlashOutline,
  CloudDownloadOutline,
  NotificationsOutline,
  BarChartOutline,
  SearchOutline,
  BookOutline
} from '@vicons/ionicons5'
import { stocksApi, portfoliosApi, filtersApi, agentsApi, dataApi, notificationsApi, tasksApi } from '../api'
import { useTaskStore } from '../stores/taskStore'
import TaskProgress from '../components/common/TaskProgress.vue'

const message = useMessage()
const taskStore = useTaskStore()
const stats = ref({ stockCount: 0, portfolioCount: 0, filterCount: 0, agentCount: 0 })
const notifications = ref<any[]>([])
const collecting = ref(false)
const collectingType = ref<string>('')

const quickActions = [
  { key: 'stocks', label: '查看股票', route: '/stocks', icon: TrendingUpOutline, color: '#00d4aa' },
  { key: 'filters', label: '创建筛选', route: '/filters', icon: SearchOutline, color: '#6366f1' },
  { key: 'backtest', label: '策略回测', route: '/backtest', icon: BarChartOutline, color: '#10b981' },
  { key: 'debate', label: '辩论分析', route: '/debate', icon: ChatbubblesOutline, color: '#f59e0b' },
]

const collectionActions = [
  { key: 'full', label: '全量采集基础指标', icon: CloudDownloadOutline, color: '#00d4aa' },
  { key: 'incremental', label: '增量更新', icon: CloudDownloadOutline, color: '#6366f1' },
  { key: 'financial', label: '全量更新财务数据', icon: BookOutline, color: '#10b981' },
]

onMounted(async () => {
  try {
    const [stockCount, portfolios, filters, agents, notifs] = await Promise.all([
      stocksApi.count(),
      portfoliosApi.list(),
      filtersApi.list(),
      agentsApi.list(),
      notificationsApi.list(),
    ])
    stats.value = {
      stockCount: stockCount.data.count,
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
  collectingType.value = type
  try {
    let res
    if (type === 'full') {
      res = await dataApi.startFullCollection()
    } else if (type === 'incremental') {
      res = await dataApi.startIncrementalUpdate()
    } else if (type === 'financial') {
      res = await dataApi.startFinancialUpdate()
    }
    const taskId = res?.data?.task_id
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
    collectingType.value = ''
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

<style scoped>
.dashboard-container {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.3s ease-out;
}

/* 统计卡片网格 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
}

.stat-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 24px;
  border-radius: 12px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  overflow: hidden;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.stat-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--card-color), transparent);
  opacity: 0.8;
}

.stat-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
  border-color: var(--card-color);
}

.stat-card-primary {
  --card-color: #00d4aa;
}

.stat-card-info {
  --card-color: #6366f1;
}

.stat-card-success {
  --card-color: #10b981;
}

.stat-card-warning {
  --card-color: #f59e0b;
}

.stat-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(8px);
}

.stat-content {
  flex: 1;
}

.stat-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 4px;
}

.stat-value {
  font-size: 32px;
  font-weight: 700;
  background: linear-gradient(135deg, var(--card-color), rgba(255, 255, 255, 0.8));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  line-height: 1;
}

/* 操作区域网格 */
.action-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
}

.action-card {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 12px !important;
  transition: all 0.3s;
}

.action-card:hover {
  border-color: var(--border-medium) !important;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
}

.quick-actions,
.collection-actions {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.action-button,
.collection-button {
  justify-content: flex-start !important;
  height: 48px !important;
  font-weight: 500 !important;
  transition: all 0.3s !important;
  border: 1px solid var(--border-subtle) !important;
  background: var(--bg-surface) !important;
}

.action-button:hover,
.collection-button:hover {
  border-color: var(--action-color) !important;
  background: rgba(255, 255, 255, 0.05) !important;
  box-shadow: 0 0 20px rgba(var(--action-color), 0.2) !important;
  transform: translateX(4px);
}

/* 任务进度容器 */
.task-progress-container {
  animation: slideDown 0.3s ease-out;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 通知卡片 */
.notification-card {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 12px !important;
}

.notification-list {
  background: transparent !important;
}

.notification-item {
  border-bottom: 1px solid var(--border-subtle) !important;
  transition: all 0.2s;
}

.notification-item:last-child {
  border-bottom: none !important;
}

.notification-item:hover {
  background: rgba(255, 255, 255, 0.02);
}

.notification-title {
  font-weight: 600;
  color: var(--text-primary);
}

.notification-content {
  color: var(--text-secondary);
  font-size: 13px;
}

/* 响应式 */
@media (max-width: 1200px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
  
  .action-grid {
    grid-template-columns: 1fr;
  }
}
</style>
