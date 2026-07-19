<template>
  <div class="page-container" v-if="detail">
    <div class="page-header">
      <div class="header-left">
        <n-icon :size="32" color="#6366f1">
          <BriefcaseOutline />
        </n-icon>
        <h2 class="page-title gradient-text">{{ detail.name }}</h2>
      </div>
    </div>

    <n-card title="添加股票" class="action-card">
      <template #header-extra>
        <n-icon :size="20" color="#00d4aa">
          <AddOutline />
        </n-icon>
      </template>
      <n-space :size="12">
        <n-input 
          v-model:value="addCode" 
          placeholder="股票代码" 
          style="width: 180px"
          size="large"
        >
          <template #prefix>
            <n-icon :size="18" color="#64748b">
              <CodeOutline />
            </n-icon>
          </template>
        </n-input>
        <n-input-number 
          v-model:value="addShares" 
          placeholder="数量" 
          style="width: 150px"
          size="large"
        >
          <template #prefix>
            <n-icon :size="18" color="#64748b">
              <CalculatorOutline />
            </n-icon>
          </template>
        </n-input-number>
        <n-button type="primary" @click="handleAdd" size="large" class="action-button">
          <template #icon>
            <n-icon :size="18">
              <AddOutline />
            </n-icon>
          </template>
          添加股票
        </n-button>
      </n-space>
    </n-card>

    <n-card title="持仓列表" class="data-card">
      <template #header-extra>
        <n-icon :size="20" color="#10b981">
          <ListOutline />
        </n-icon>
      </template>
      <n-data-table 
        :columns="columns" 
        :data="detail.holdings"
        :bordered="false"
      />
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, h, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { NButton, NTag, useMessage } from 'naive-ui'
import { 
  BriefcaseOutline, 
  AddOutline, 
  CodeOutline,
  CalculatorOutline,
  ListOutline,
  TrashOutline
} from '@vicons/ionicons5'
import { portfoliosApi } from '../api'
import type { PortfolioDetail } from '../types'

const route = useRoute()
const message = useMessage()
const id = Number(route.params.id)
const detail = ref<PortfolioDetail | null>(null)
const addCode = ref('')
const addShares = ref(100)

const columns = [
  { 
    title: '代码', 
    key: 'stock_code',
    render: (row: any) => h(NTag, { 
      size: 'small',
      type: 'info',
      round: true
    }, { default: () => row.stock_code })
  },
  { 
    title: '名称', 
    key: 'stock_name',
    render: (row: any) => h('span', { 
      style: 'font-weight: 600; color: var(--text-primary);'
    }, row.stock_name)
  },
  { 
    title: '数量', 
    key: 'shares',
    render: (row: any) => h('span', { 
      style: 'font-weight: 500; color: var(--text-secondary);'
    }, row.shares.toLocaleString())
  },
  { 
    title: '成本', 
    key: 'avg_cost',
    render: (row: any) => h('span', { 
      style: 'font-weight: 500; color: var(--text-secondary);'
    }, `¥${row.avg_cost.toFixed(2)}`)
  },
  {
    title: '操作', 
    key: 'actions',
    render: (row: any) => h(NButton, { 
      size: 'small', 
      type: 'error',
      ghost: true,
      onClick: () => handleRemove(row.id)
    }, { 
      default: () => [
        h(NIcon, { size: 14, style: 'margin-right: 4px;' }, { default: () => h(TrashOutline) }),
        '移除'
      ]
    }),
  },
]

async function load() {
  const res = await portfoliosApi.get(id)
  detail.value = res.data
}

async function handleAdd() {
  if (!addCode.value.trim()) {
    message.warning('请输入股票代码')
    return
  }
  await portfoliosApi.addStock(id, addCode.value.trim(), addShares.value)
  message.success('已添加')
  addCode.value = ''
  await load()
}

async function handleRemove(itemId: number) {
  await portfoliosApi.removeStockById(id, itemId)
  message.success('已移除')
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

.action-card :deep(.n-input),
.action-card :deep(.n-input-number) {
  background: rgba(30, 41, 59, 0.6) !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 8px !important;
  transition: all 0.3s !important;
}

.action-card :deep(.n-input:hover),
.action-card :deep(.n-input-number:hover) {
  border-color: var(--primary) !important;
  background: rgba(30, 41, 59, 0.8) !important;
}

.action-card :deep(.n-input--focus),
.action-card :deep(.n-input-number--focus) {
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
