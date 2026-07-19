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
        <n-auto-complete
          v-model:value="addCode"
          :options="searchResults"
          :loading="searching"
          placeholder="输入代码、名称、拼音或首字母"
          style="width: 280px"
          size="large"
          @update:value="handleSearch"
          @select="handleSelect"
          clearable
        >
          <template #prefix>
            <n-icon :size="18" color="#64748b">
              <SearchOutline />
            </n-icon>
          </template>
        </n-auto-complete>
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
import { ref, h, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { NButton, NTag, NIcon, useMessage } from 'naive-ui'
import { 
  BriefcaseOutline, 
  AddOutline, 
  SearchOutline,
  CalculatorOutline,
  ListOutline,
  TrashOutline
} from '@vicons/ionicons5'
import { portfoliosApi, stocksApi } from '../api'
import type { PortfolioDetail, Stock } from '../types'

const route = useRoute()
const message = useMessage()
const id = computed(() => Number(route.params.id))
const detail = ref<PortfolioDetail | null>(null)
const addCode = ref('')
const addShares = ref(100)
const searchResults = ref<any[]>([])
const searching = ref(false)
let searchTimeout: ReturnType<typeof setTimeout> | null = null

async function handleSearch(value: string) {
  // Clear previous timeout
  if (searchTimeout) {
    clearTimeout(searchTimeout)
  }
  
  // If empty, clear results
  if (!value || value.trim().length === 0) {
    searchResults.value = []
    return
  }
  
  // Debounce search
  searchTimeout = setTimeout(async () => {
    searching.value = true
    try {
      const res = await stocksApi.search(value.trim())
      searchResults.value = res.data.map((stock: Stock) => ({
        label: `${stock.code} ${stock.name}`,
        value: stock.code,
        stock: stock
      }))
    } catch (e: any) {
      console.error('Search failed:', e)
      searchResults.value = []
    } finally {
      searching.value = false
    }
  }, 300)
}

function handleSelect(value: string) {
  // When user selects from dropdown, ensure we only keep the code
  addCode.value = value
}

const columns = [
  { 
    title: '代码', 
    key: 'stock_code',
    width: 90,
    render: (row: any) => h(NTag, { 
      size: 'small',
      type: 'info',
      round: true
    }, { default: () => row.stock_code })
  },
  { 
    title: '名称', 
    key: 'stock_name',
    width: 100,
    render: (row: any) => h('span', { 
      style: 'font-weight: 600; color: var(--text-primary);'
    }, row.stock_name)
  },
  { 
    title: '现价', 
    key: 'price',
    width: 80,
    render: (row: any) => h('span', { 
      style: `color: ${row.pricechange > 0 ? '#e74c3c' : row.pricechange < 0 ? '#27ae60' : 'var(--text-primary)'}; font-weight: 600;`
    }, row.price ? '¥' + row.price.toFixed(2) : '-')
  },
  { 
    title: '涨跌幅', 
    key: 'changepercent',
    width: 80,
    render: (row: any) => h('span', { 
      style: `color: ${row.changepercent > 0 ? '#e74c3c' : row.changepercent < 0 ? '#27ae60' : 'var(--text-secondary)'}; font-weight: 600;`
    }, row.changepercent != null ? `${row.changepercent > 0 ? '+' : ''}${row.changepercent.toFixed(2)}%` : '-')
  },
  { 
    title: '数量', 
    key: 'shares',
    width: 80,
    render: (row: any) => h('span', { 
      style: 'font-weight: 500; color: var(--text-secondary);'
    }, row.shares.toLocaleString())
  },
  { 
    title: '成本', 
    key: 'avg_cost',
    width: 80,
    render: (row: any) => h('span', { 
      style: 'font-weight: 500; color: var(--text-secondary);'
    }, `¥${row.avg_cost.toFixed(2)}`)
  },
  { 
    title: 'PE', 
    key: 'per',
    width: 70,
    render: (row: any) => h('span', { 
      style: `color: ${row.per && row.per > 0 ? '#10b981' : 'var(--text-secondary)'}; font-weight: 500;`
    }, row.per ? row.per.toFixed(1) : '-')
  },
  { 
    title: 'PB', 
    key: 'pb',
    width: 70,
    render: (row: any) => h('span', { 
      style: `color: ${row.pb && row.pb > 0 ? '#6366f1' : 'var(--text-secondary)'}; font-weight: 500;`
    }, row.pb ? row.pb.toFixed(2) : '-')
  },
  { 
    title: '市值(亿)', 
    key: 'mktcap',
    width: 100,
    render: (row: any) => h('span', { 
      style: 'color: var(--text-primary); font-weight: 500;'
    }, row.mktcap ? (row.mktcap / 10000).toFixed(2) : '-')
  },
  {
    title: '操作', 
    key: 'actions',
    width: 80,
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
  try {
    const res = await portfoliosApi.get(id.value)
    detail.value = res.data
  } catch (e: any) {
    message.error('加载组合详情失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function handleAdd() {
  if (!addCode.value.trim()) {
    message.warning('请输入股票代码')
    return
  }
  
  // Extract just the 6-digit code from input (handles cases like "001359 平安电工")
  const input = addCode.value.trim()
  const codeMatch = input.match(/^\d{6}/)
  if (!codeMatch) {
    // Try to find any 6-digit sequence in the input
    const anyMatch = input.match(/\d{6}/)
    if (!anyMatch) {
      message.warning('请输入有效的6位股票代码')
      return
    }
    addCode.value = anyMatch[0]
  } else {
    addCode.value = codeMatch[0]
  }
  
  try {
    await portfoliosApi.addStock(id.value, addCode.value, addShares.value)
    message.success('已添加')
    addCode.value = ''
    await load()
  } catch (e: any) {
    message.error('添加失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function handleRemove(itemId: number) {
  try {
    await portfoliosApi.removeStockById(id.value, itemId)
    message.success('已移除')
    await load()
  } catch (e: any) {
    message.error('移除失败: ' + (e.response?.data?.detail || e.message))
  }
}

onMounted(load)

watch(id, () => {
  load()
})
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
