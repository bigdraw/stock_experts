<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-left">
        <n-icon :size="32" color="#f59e0b">
          <NotificationsOutline />
        </n-icon>
        <h2 class="page-title gradient-text">告警管理</h2>
      </div>
    </div>

    <n-card title="创建告警" class="action-card">
      <template #header-extra>
        <n-icon :size="20" color="#00d4aa">
          <AddOutline />
        </n-icon>
      </template>
      <n-form class="alert-form">
        <n-grid :cols="2" :x-gap="16">
          <n-gi>
            <n-form-item label="告警名称">
              <n-input v-model:value="name" placeholder="例：ROE告警" size="large">
                <template #prefix>
                  <n-icon :size="18" color="#64748b">
                    <PrismOutline />
                  </n-icon>
                </template>
              </n-input>
            </n-form-item>
          </n-gi>
          <n-gi>
            <n-form-item label="条件描述">
              <n-input v-model:value="condition" placeholder="例：ROE大于20%" size="large">
                <template #prefix>
                  <n-icon :size="18" color="#64748b">
                    <FilterOutline />
                  </n-icon>
                </template>
              </n-input>
            </n-form-item>
          </n-gi>
        </n-grid>
        <n-button type="primary" @click="handleCreate" size="large" class="action-button">
          <template #icon>
            <n-icon :size="18">
              <AddOutline />
            </n-icon>
          </template>
          创建告警
        </n-button>
      </n-form>
    </n-card>

    <n-card title="告警列表" class="data-card">
      <template #header-extra>
        <n-icon :size="20" color="#6366f1">
          <ListOutline />
        </n-icon>
      </template>
      <n-data-table 
        :columns="columns" 
        :data="alerts" 
        :loading="loading"
        :bordered="false"
      />
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, h, onMounted } from 'vue'
import { NButton, NSwitch, NTag, NIcon, useMessage } from 'naive-ui'
import { 
  NotificationsOutline, 
  AddOutline, 
  PrismOutline,
  FilterOutline,
  ListOutline,
  TrashOutline
} from '@vicons/ionicons5'
import { alertsApi } from '../api'
import type { Alert } from '../types'

const message = useMessage()
const alerts = ref<Alert[]>([])
const loading = ref(false)
const name = ref('')
const condition = ref('')

const columns = [
  { 
    title: '名称', 
    key: 'name',
    render: (row: Alert) => h('span', { 
      style: 'font-weight: 600; color: var(--text-primary);'
    }, row.name)
  },
  { 
    title: '条件', 
    key: 'nl_condition',
    render: (row: Alert) => h('span', { 
      style: 'color: var(--text-secondary); font-size: 13px;'
    }, row.nl_condition)
  },
  { 
    title: '状态', 
    key: 'is_active',
    render: (row: Alert) => h('div', { style: 'display: flex; align-items: center; gap: 8px;' }, [
      h(NSwitch, { 
        value: row.is_active, 
        onUpdateValue: () => handleToggle(row.id),
        size: 'medium'
      }),
      h(NTag, { 
        size: 'small',
        type: row.is_active ? 'success' : 'default',
        round: true
      }, { default: () => row.is_active ? '启用' : '禁用' })
    ])
  },
  {
    title: '操作', 
    key: 'actions',
    width: 120,
    render: (row: Alert) => h(NButton, { 
      size: 'small', 
      type: 'error',
      ghost: true,
      onClick: () => handleDelete(row.id)
    }, { 
      default: () => [
        h(NIcon, { size: 14, style: 'margin-right: 4px;' }, { default: () => h(TrashOutline) }),
        '删除'
      ]
    }),
  },
]

async function load() {
  loading.value = true
  try {
    const res = await alertsApi.list()
    alerts.value = res.data
  } finally {
    loading.value = false
  }
}

async function handleCreate() {
  if (!name.value.trim()) {
    message.warning('请输入告警名称')
    return
  }
  if (!condition.value.trim()) {
    message.warning('请输入告警条件')
    return
  }
  await alertsApi.create(name.value.trim(), condition.value.trim())
  message.success('告警创建成功')
  name.value = ''
  condition.value = ''
  await load()
}

async function handleToggle(id: number) {
  await alertsApi.toggle(id)
  await load()
}

async function handleDelete(id: number) {
  await alertsApi.delete(id)
  message.success('已删除')
  await load()
}

onMounted(load)
</script>

<style scoped>
.page-container {
  animation: fadeIn 0.3s ease-out;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 2px solid var(--border-subtle);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-title {
  font-size: 28px;
  font-weight: 700;
  margin: 0;
  letter-spacing: -0.5px;
}

.action-card,
.data-card {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 12px !important;
  margin-bottom: 20px;
  transition: all 0.3s;
}

.action-card:hover,
.data-card:hover {
  border-color: var(--border-medium) !important;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
}

.action-card :deep(.n-card-header),
.data-card :deep(.n-card-header) {
  border-bottom: 1px solid var(--border-subtle);
}

.action-card :deep(.n-card-header__main),
.data-card :deep(.n-card-header__main) {
  font-weight: 600;
  font-size: 18px;
  color: var(--text-primary);
}

.alert-form :deep(.n-form-item-label) {
  font-weight: 600;
  color: var(--text-secondary);
}

.alert-form :deep(.n-input) {
  background: rgba(30, 41, 59, 0.6) !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 8px !important;
  transition: all 0.3s !important;
}

.alert-form :deep(.n-input:hover) {
  border-color: var(--primary) !important;
  background: rgba(30, 41, 59, 0.8) !important;
}

.alert-form :deep(.n-input--focus) {
  border-color: var(--primary) !important;
  box-shadow: 0 0 0 2px rgba(0, 212, 170, 0.15) !important;
  background: rgba(30, 41, 59, 0.9) !important;
}

.action-button {
  background: linear-gradient(135deg, #00d4aa 0%, #6366f1 100%) !important;
  border: none !important;
  font-weight: 600 !important;
  transition: all 0.3s !important;
  margin-top: 8px;
}

.action-button:hover {
  box-shadow: 0 8px 24px rgba(0, 212, 170, 0.4) !important;
  transform: translateY(-2px);
}

.data-card :deep(.n-data-table) {
  background: transparent !important;
}

.data-card :deep(.n-data-table-thead) {
  background: rgba(30, 41, 59, 0.6) !important;
}

.data-card :deep(.n-data-table-th) {
  background: transparent !important;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  font-size: 12px;
  letter-spacing: 0.5px;
}

.data-card :deep(.n-data-table-td) {
  border-bottom: 1px solid var(--border-subtle) !important;
  transition: all 0.2s;
}

.data-card :deep(.n-data-table-tr:hover .n-data-table-td) {
  background: rgba(0, 212, 170, 0.05) !important;
}

.data-card :deep(.n-data-table-tr:hover .n-data-table-td::before) {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: linear-gradient(180deg, #00d4aa 0%, #6366f1 100%);
  animation: slideIn 0.2s ease-out;
}

@keyframes slideIn {
  from {
    transform: scaleY(0);
  }
  to {
    transform: scaleY(1);
  }
}

.data-card :deep(.n-data-table-tr:nth-child(even) .n-data-table-td) {
  background: rgba(30, 41, 59, 0.3);
}

.data-card :deep(.n-switch__rail) {
  background: rgba(30, 41, 59, 0.8);
}

.data-card :deep(.n-switch__rail--active) {
  background: linear-gradient(135deg, #00d4aa 0%, #6366f1 100%);
}
</style>
