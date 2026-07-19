<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-left">
        <n-icon :size="32" color="#10b981">
          <FunnelOutline />
        </n-icon>
        <h2 class="page-title gradient-text">筛选工具库</h2>
      </div>
    </div>

    <n-card title="创建筛选脚本" class="action-card">
      <template #header-extra>
        <n-icon :size="20" color="#00d4aa">
          <CreateOutline />
        </n-icon>
      </template>
      <n-form class="create-form">
        <n-form-item label="筛选名称">
          <n-input v-model:value="name" placeholder="例：高ROE低PE" size="large">
            <template #prefix>
              <n-icon :size="18" color="#64748b">
                <PrismOutline />
              </n-icon>
            </template>
          </n-input>
        </n-form-item>
        <n-form-item label="自然语言描述">
          <n-input 
            v-model:value="nlDesc" 
            type="textarea" 
            placeholder="例：ROE大于15%且市盈率小于20的盈利股票" 
            :rows="4"
            size="large"
          />
        </n-form-item>
        <n-button type="primary" :loading="generating" @click="handleGenerate" size="large" class="action-button">
          <template #icon>
            <n-icon :size="18">
              <SparklesOutline />
            </n-icon>
          </template>
          生成筛选脚本
        </n-button>
      </n-form>
    </n-card>

    <n-card title="工具库" class="data-card">
      <template #header-extra>
        <n-icon :size="20" color="#6366f1">
          <LibraryOutline />
        </n-icon>
      </template>
      <n-data-table 
        :columns="columns" 
        :data="filters" 
        :loading="loading"
        :bordered="false"
      />
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, h, onMounted } from 'vue'
import { NButton, NSpace, NTag, useMessage } from 'naive-ui'
import { 
  FunnelOutline, 
  CreateOutline, 
  PrismOutline,
  SparklesOutline,
  LibraryOutline,
  PlayOutline,
  TrashOutline
} from '@vicons/ionicons5'
import { filtersApi } from '../api'
import type { FilterScript } from '../types'

const message = useMessage()
const filters = ref<FilterScript[]>([])
const loading = ref(false)
const generating = ref(false)
const name = ref('')
const nlDesc = ref('')

const columns = [
  { 
    title: 'ID', 
    key: 'id', 
    width: 80,
    render: (row: FilterScript) => h(NTag, { 
      size: 'small',
      type: 'default',
      round: true
    }, { default: () => `#${row.id}` })
  },
  { 
    title: '名称', 
    key: 'name', 
    width: 200,
    render: (row: FilterScript) => h('span', { 
      style: 'font-weight: 600; color: var(--text-primary);'
    }, row.name)
  },
  { 
    title: '描述', 
    key: 'nl_description',
    render: (row: FilterScript) => h('span', { 
      style: 'color: var(--text-secondary); font-size: 13px;'
    }, row.nl_description)
  },
  { 
    title: '使用次数', 
    key: 'usage_count', 
    width: 120,
    render: (row: FilterScript) => h(NTag, { 
      size: 'small',
      type: 'info',
      round: true
    }, { default: () => `${row.usage_count} 次` })
  },
  {
    title: '操作', 
    key: 'actions', 
    width: 200,
    render: (row: FilterScript) => h(NSpace, { size: 8 }, {
      default: () => [
        h(NButton, { 
          size: 'small', 
          type: 'primary',
          ghost: true,
          onClick: () => handleExecute(row.id)
        }, { 
          default: () => [
            h(NIcon, { size: 14, style: 'margin-right: 4px;' }, { default: () => h(PlayOutline) }),
            '执行'
          ]
        }),
        h(NButton, { 
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
      ],
    }),
  },
]

async function load() {
  loading.value = true
  try {
    const res = await filtersApi.list()
    filters.value = res.data
  } finally {
    loading.value = false
  }
}

async function handleGenerate() {
  if (!name.value.trim()) {
    message.warning('请输入筛选名称')
    return
  }
  if (!nlDesc.value.trim()) {
    message.warning('请输入筛选条件描述')
    return
  }
  generating.value = true
  try {
    await filtersApi.generate(name.value.trim(), nlDesc.value.trim())
    message.success('筛选脚本已生成')
    name.value = ''
    nlDesc.value = ''
    await load()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '生成失败')
  } finally {
    generating.value = false
  }
}

async function handleExecute(id: number) {
  try {
    const res = await filtersApi.execute(id)
    message.success(`筛选结果：${res.data.count} 只股票`)
  } catch (e: any) {
    message.error('执行失败')
  }
}

async function handleDelete(id: number) {
  await filtersApi.delete(id)
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

.create-form :deep(.n-form-item-label) {
  font-weight: 600;
  color: var(--text-secondary);
}

.create-form :deep(.n-input) {
  background: rgba(30, 41, 59, 0.6) !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 8px !important;
  transition: all 0.3s !important;
}

.create-form :deep(.n-input:hover) {
  border-color: var(--primary) !important;
  background: rgba(30, 41, 59, 0.8) !important;
}

.create-form :deep(.n-input--focus) {
  border-color: var(--primary) !important;
  box-shadow: 0 0 0 2px rgba(0, 212, 170, 0.15) !important;
  background: rgba(30, 41, 59, 0.9) !important;
}

.action-button {
  background: linear-gradient(135deg, #00d4aa 0%, #6366f1 100%) !important;
  border: none !important;
  font-weight: 600 !important;
  transition: all 0.3s !important;
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
</style>
