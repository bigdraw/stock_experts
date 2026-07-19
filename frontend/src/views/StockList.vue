<template>
  <div class="page-container">
    <n-space vertical :size="20">
      <n-auto-complete
        v-model:value="search"
        :options="searchOptions"
        :loading="searching"
        placeholder="搜索代码、名称、拼音或首字母..."
        clearable
        size="large"
        @update:value="handleSearch"
        @select="handleSelect"
      >
        <template #prefix>
          <n-icon :size="18" color="#64748b">
            <SearchOutline />
          </n-icon>
        </template>
      </n-auto-complete>
      
      <n-card class="data-card">
        <n-data-table 
          :columns="columns" 
          :data="stocks" 
          :loading="loading" 
          :pagination="{ pageSize: 50 }"
          :bordered="false"
        />
      </n-card>
    </n-space>
  </div>
</template>

<script setup lang="ts">
import { ref, h, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NTag } from 'naive-ui'
import { SearchOutline } from '@vicons/ionicons5'
import { stocksApi } from '../api'
import type { Stock } from '../types'

const router = useRouter()
const stocks = ref<Stock[]>([])
const loading = ref(false)
const search = ref('')
const searchOptions = ref<any[]>([])
const searching = ref(false)
let searchTimeout: ReturnType<typeof setTimeout> | null = null

const columns = [
  { 
    title: '代码', 
    key: 'code', 
    width: 120,
    render: (row: Stock) => h(NTag, { 
      size: 'small',
      type: 'info',
      round: true
    }, { default: () => row.code })
  },
  { 
    title: '名称', 
    key: 'name', 
    width: 150,
    render: (row: Stock) => h('span', { 
      style: 'font-weight: 600; color: var(--text-primary);'
    }, row.name)
  },
  { 
    title: '市场', 
    key: 'market', 
    width: 80,
    render: (row: Stock) => h(NTag, { 
      size: 'small',
      type: row.market === 'SH' ? 'success' : 'warning',
      round: true
    }, { default: () => row.market })
  },
  { 
    title: '行业', 
    key: 'industry', 
    width: 150,
    render: (row: Stock) => h('span', { 
      style: 'color: var(--text-secondary);'
    }, row.industry || '-')
  },
  {
    title: '操作', 
    key: 'actions', 
    width: 120,
    render: (row: Stock) => h(NButton, { 
      size: 'small',
      type: 'primary',
      ghost: true,
      onClick: () => router.push(`/stocks/${row.code}`)
    }, { default: () => '查看详情' }),
  },
]

async function loadStocks() {
  loading.value = true
  try {
    const res = await stocksApi.list({ limit: 500 })
    stocks.value = res.data
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

function handleSearch(value: string) {
  if (searchTimeout) {
    clearTimeout(searchTimeout)
  }

  if (!value || !value.trim()) {
    searchOptions.value = []
    loadStocks()
    return
  }

  searchTimeout = setTimeout(async () => {
    searching.value = true
    try {
      const res = await stocksApi.search(value.trim(), 20)
      // 更新下拉候选列表
      searchOptions.value = res.data.map((stock: Stock) => ({
        label: `${stock.code} ${stock.name}`,
        value: stock.code
      }))
      // 同时更新表格
      stocks.value = res.data
    } catch (e) {
      console.error(e)
      searchOptions.value = []
    } finally {
      searching.value = false
    }
  }, 300)
}

function handleSelect(value: string) {
  // 选中后跳转到股票详情
  router.push(`/stocks/${value}`)
}

onMounted(loadStocks)
</script>

<style scoped>
.page-container {
  animation: fadeIn 0.3s ease-out;
}

.page-container :deep(.n-input),
.page-container :deep(.n-base-selection .n-base-selection-input) {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 12px !important;
  transition: all 0.3s !important;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.page-container :deep(.n-input:hover),
.page-container :deep(.n-base-selection:hover .n-base-selection-input) {
  border-color: var(--primary) !important;
  background: var(--bg-elevated) !important;
  box-shadow: 0 4px 16px rgba(0, 212, 170, 0.15) !important;
}

.page-container :deep(.n-input--focus),
.page-container :deep(.n-base-selection--focus .n-base-selection-input) {
  border-color: var(--primary) !important;
  box-shadow: 0 0 0 3px rgba(0, 212, 170, 0.15) !important;
  background: var(--bg-elevated) !important;
}

.data-card {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 12px !important;
  overflow: hidden;
  transition: all 0.3s;
}

.data-card:hover {
  border-color: var(--border-medium) !important;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
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

.data-card :deep(.n-pagination) {
  margin-top: 20px;
  padding: 16px;
  background: rgba(30, 41, 59, 0.4);
  border-radius: 8px;
}
</style>
