<template>
  <div class="page-container">
    <!-- 空状态：没有投资组合 -->
    <n-empty 
      v-if="!loading && portfolios.length === 0"
      description="还没有自选股组合"
      size="large"
      class="empty-state"
    >
      <template #extra>
        <n-button type="primary" @click="showCreatePortfolio = true">
          创建自选组合
        </n-button>
      </template>
    </n-empty>

    <!-- 有投资组合时显示标签页 -->
    <div v-else class="content-container">
      <n-tabs 
        v-model:value="activePortfolioId" 
        type="line"
        @update:value="handlePortfolioChange"
      >
        <n-tab-pane 
          v-for="portfolio in portfolios" 
          :key="portfolio.id" 
          :name="portfolio.id"
          :tab="portfolio.name"
        >
          <!-- 搜索框 -->
          <n-input 
            v-model:value="search" 
            placeholder="搜索代码、名称、拼音或首字母..." 
            clearable 
            @update:value="handleSearch"
            size="large"
            class="search-input"
          >
            <template #prefix>
              <n-icon :size="18" color="#64748b">
                <SearchOutline />
              </n-icon>
            </template>
          </n-input>

          <!-- 股票列表 -->
          <n-card class="data-card">
            <n-data-table 
              :columns="columns" 
              :data="stocks" 
              :loading="loading" 
              :pagination="{ pageSize: 50 }"
              :bordered="false"
            />
          </n-card>
        </n-tab-pane>
      </n-tabs>

      <!-- 创建新组合按钮 -->
      <div class="create-portfolio-section">
        <n-button 
          type="primary" 
          ghost 
          @click="showCreatePortfolio = true"
        >
          <template #icon>
            <n-icon><AddOutline /></n-icon>
          </template>
          创建新组合
        </n-button>
      </div>
    </div>

    <!-- 创建组合对话框 -->
    <n-modal 
      v-model:show="showCreatePortfolio"
      preset="dialog"
      title="创建自选组合"
      positive-text="创建"
      negative-text="取消"
      @positive-click="handleCreatePortfolio"
      @negative-click="showCreatePortfolio = false"
    >
      <n-form>
        <n-form-item label="组合名称">
          <n-input v-model:value="newPortfolioName" placeholder="输入组合名称" />
        </n-form-item>
        <n-form-item label="描述">
          <n-input 
            v-model:value="newPortfolioDescription" 
            type="textarea" 
            placeholder="输入组合描述（可选）"
            :rows="3"
          />
        </n-form-item>
      </n-form>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, h, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NTag, useMessage } from 'naive-ui'
import { SearchOutline, AddOutline } from '@vicons/ionicons5'
import { stocksApi, portfoliosApi } from '../api'
import type { Stock, Portfolio, PortfolioDetail } from '../types'

const router = useRouter()
const message = useMessage()

// 状态
const portfolios = ref<Portfolio[]>([])
const activePortfolioId = ref<number | null>(null)
const activePortfolio = ref<PortfolioDetail | null>(null)
const stocks = ref<Stock[]>([])
const loading = ref(false)
const search = ref('')
const showCreatePortfolio = ref(false)
const newPortfolioName = ref('')
const newPortfolioDescription = ref('')

let searchTimeout: ReturnType<typeof setTimeout> | null = null

// 表格列定义
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

// 加载投资组合列表
async function loadPortfolios() {
  loading.value = true
  try {
    const res = await portfoliosApi.list()
    portfolios.value = res.data
    
    // 如果有投资组合，默认选中第一个
    if (portfolios.value.length > 0 && !activePortfolioId.value) {
      activePortfolioId.value = portfolios.value[0].id
      await loadPortfolioDetail(activePortfolioId.value)
    }
  } catch (e) {
    console.error('Failed to load portfolios:', e)
    message.error('加载投资组合失败')
  } finally {
    loading.value = false
  }
}

// 加载投资组合详情
async function loadPortfolioDetail(portfolioId: number) {
  loading.value = true
  try {
    const res = await portfoliosApi.get(portfolioId)
    activePortfolio.value = res.data
    
    // 将持仓转换为 Stock 类型
    stocks.value = res.data.holdings.map(holding => ({
      code: holding.stock_code,
      name: holding.stock_name,
      market: holding.stock_code.startsWith('6') ? 'SH' : 'SZ',
      industry: '', // 持仓数据中没有行业信息
      is_active: true
    }))
  } catch (e) {
    console.error('Failed to load portfolio detail:', e)
    message.error('加载组合详情失败')
  } finally {
    loading.value = false
  }
}

// 切换投资组合
function handlePortfolioChange(portfolioId: number) {
  activePortfolioId.value = portfolioId
  loadPortfolioDetail(portfolioId)
}

// 搜索股票
function handleSearch(value: string) {
  if (searchTimeout) {
    clearTimeout(searchTimeout)
  }

  if (!value || !value.trim()) {
    // 清空搜索时，重新加载当前组合的持仓
    if (activePortfolioId.value) {
      loadPortfolioDetail(activePortfolioId.value)
    }
    return
  }

  searchTimeout = setTimeout(async () => {
    loading.value = true
    try {
      const res = await stocksApi.search(value.trim(), 100)
      stocks.value = res.data || []
    } catch (e: any) {
      console.error('Search failed:', e.response?.data || e.message)
      message.error('搜索失败')
    } finally {
      loading.value = false
    }
  }, 300)
}

// 创建投资组合
async function handleCreatePortfolio() {
  if (!newPortfolioName.value.trim()) {
    message.warning('请输入组合名称')
    return false
  }

  try {
    const res = await portfoliosApi.create(
      newPortfolioName.value.trim(),
      newPortfolioDescription.value.trim()
    )
    
    message.success('组合创建成功')
    
    // 重新加载投资组合列表
    await loadPortfolios()
    
    // 选中新创建的组合
    activePortfolioId.value = res.data.id
    await loadPortfolioDetail(res.data.id)
    
    // 清空表单
    newPortfolioName.value = ''
    newPortfolioDescription.value = ''
    
    return true
  } catch (e: any) {
    console.error('Failed to create portfolio:', e)
    message.error('创建组合失败')
    return false
  }
}

// 初始化
onMounted(() => {
  loadPortfolios()
})
</script>

<style scoped>
.page-container {
  animation: fadeIn 0.3s ease-out;
  min-height: calc(100vh - 100px);
}

.empty-state {
  margin-top: 100px;
}

.content-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.search-input {
  margin-bottom: 20px;
}

.search-input :deep(.n-input) {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 12px !important;
  transition: all 0.3s !important;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.search-input :deep(.n-input:hover) {
  border-color: var(--primary) !important;
  background: var(--bg-elevated) !important;
  box-shadow: 0 4px 16px rgba(0, 212, 170, 0.15) !important;
}

.search-input :deep(.n-input--focus) {
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

.create-portfolio-section {
  margin-top: 20px;
  text-align: center;
}

:deep(.n-tabs-nav) {
  background: var(--bg-elevated);
  border-radius: 12px;
  padding: 8px;
  margin-bottom: 20px;
}

:deep(.n-tabs-tab) {
  border-radius: 8px;
  transition: all 0.3s;
}

:deep(.n-tabs-tab--active) {
  background: linear-gradient(135deg, rgba(0, 212, 170, 0.1) 0%, rgba(99, 102, 241, 0.1) 100%);
  color: var(--primary);
}
</style>
