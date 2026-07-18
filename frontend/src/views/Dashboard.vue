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
            <n-button @click="startCollection('full')" :loading="collecting">全量采集基础指标</n-button>
            <n-button @click="startCollection('incremental')" :loading="collecting">增量更新</n-button>
          </n-space>
        </n-card>
      </n-gi>
    </n-grid>

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
import { stocksApi, portfoliosApi, filtersApi, agentsApi, dataApi, notificationsApi } from '../api'

const message = useMessage()
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
})

async function startCollection(type: string) {
  collecting.value = true
  try {
    if (type === 'full') {
      await dataApi.startFullCollection()
    } else {
      await dataApi.startIncrementalUpdate()
    }
    message.success('数据采集任务已启动')
  } catch (e: any) {
    message.error('启动失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    collecting.value = false
  }
}
</script>
