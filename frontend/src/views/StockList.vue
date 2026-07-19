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

    <!-- 有投资组合时显示内容 -->
    <div v-else class="content-container">
      <!-- 搜索框（顶部，不影响下方表格） -->
      <div class="search-section">
        <n-auto-complete
          v-model:value="search"
          :options="searchOptions"
          :loading="searching"
          placeholder="搜索代码、名称、拼音或首字母..."
          clearable
          size="large"
          class="search-autocomplete"
          @update:value="handleSearch"
          @select="handleSearchSelect"
        >
          <template #prefix>
            <n-icon :size="18" color="#64748b">
              <SearchOutline />
            </n-icon>
          </template>
        </n-auto-complete>
      </div>

      <!-- 投资组合标签页 -->
      <div class="tabs-section">
        <n-tabs 
          v-model:value="activePortfolioId" 
          type="card"
          @update:value="handlePortfolioChange"
          class="portfolio-tabs"
        >
          <n-tab-pane 
            v-for="portfolio in portfolios" 
            :key="portfolio.id" 
            :name="portfolio.id"
            :tab="portfolio.name"
          >
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
import { ref, h, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NTag, NSpace, useMessage } from 'naive-ui'
import { SearchOutline, AddOutline, EyeOutline, AddCircleOutline } from '@vicons/ionicons5'
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
const searchOptions = ref<any[]>([])
const searching = ref(false)
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
      industry: '',
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

// 搜索股票（只更新下拉候选，不影响表格）
function handleSearch(value: string) {
  if (searchTimeout) {
    clearTimeout(searchTimeout)
  }

  if (!value || !value.trim()) {
    searchOptions.value = []
    return
  }

  searchTimeout = setTimeout(async () => {
    searching.value = true
    try {
      const res = await stocksApi.search(value.trim(), 20)
      const results = res.data || []
      
      // 构建丰富的下拉选项
      searchOptions.value = results.map((stock: Stock) => ({
        label: `${stock.code} ${stock.name}`,
        value: stock.code,
        stock: stock,
        // 自定义渲染
        render: () => {
          return h('div', { class: 'search-option-item' }, [
            h('div', { class: 'search-option-main' }, [
              h(NTag, { size: 'small', type: 'info', round: true }, { default: () => stock.code }),
              h('span', { class: 'search-option-name' }, stock.name),
              h(NTag, { 
                size: 'tiny', 
                type: stock.market === 'SH' ? 'success' : 'warning',
                round: true,
                style: 'margin-left: 8px;'
              }, { default: () => stock.market })
            ]),
            h('div', { class: 'search-option-actions' }, [
              h(NButton, {
                size: 'tiny',
                type: 'info',
                ghost: true,
                onClick: (e: Event) => {
                  e.stopPropagation()
                  router.push(`/stocks/${stock.code}`)
                }
              }, {
                icon: () => h(EyeOutline, { size: 14 }),
                default: () => '详情'
              }),
              h(NButton, {
                size: 'tiny',
                type: 'primary',
                ghost: true,
                onClick: (e: Event) => {
                  e.stopPropagation()
                  handleAddToPortfolio(stock.code)
                }
              }, {
                icon: () => h(AddCircleOutline, { size: 14 }),
                default: () => '添加'
              })
            ])
          ])
        }
      }))
    } catch (e: any) {
      console.error('Search failed:', e.response?.data || e.message)
      searchOptions.value = []
    } finally {
      searching.value = false
    }
  }, 300)
}

// 选中搜索结果时清空搜索框
function handleSearchSelect(value: string) {
  search.value = ''
  searchOptions.value = []
}

// 添加股票到当前组合
async function handleAddToPortfolio(stockCode: string) {
  if (!activePortfolioId.value) {
    message.warning('请先创建或选择一个组合')
    return
  }

  try {
    await portfoliosApi.addStock(activePortfolioId.value, stockCode)
    message.success(`已添加 ${stockCode} 到当前组合`)
    
    // 刷新当前组合
    await loadPortfolioDetail(activePortfolioId.value)
    
    // 清空搜索
    search.value = ''
    searchOptions.value = []
  } catch (e: any) {
    console.error('Failed to add stock:', e)
    message.error('添加股票失败')
  }
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

/* 搜索区域 */
.search-section {
  margin-bottom: 20px;
}

.search-autocomplete {
  max-width: 600px;
}

.search-autocomplete :deep(.n-input) {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 12px !important;
  transition: all 0.3s !important;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.search-autocomplete :deep(.n-input:hover) {
  border-color: var(--primary) !important;
  background: var(--bg-elevated) !important;
  box-shadow: 0 4px 16px rgba(0, 212, 170, 0.15) !important;
}

.search-autocomplete :deep(.n-input--focus) {
  border-color: var(--primary) !important;
  box-shadow: 0 0 0 3px rgba(0, 212, 170, 0.15) !important;
  background: var(--bg-elevated) !important;
}

/* 搜索下拉选项样式 */
:deep(.search-option-item) {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  width: 100%;
}

:deep(.search-option-main) {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

:deep(.search-option-name) {
  font-weight: 600;
  color: var(--text-primary);
  margin-left: 8px;
}

:deep(.search-option-actions) {
  display: flex;
  gap: 8px;
  margin-left: 16px;
}

/* 标签页区域 */
.tabs-section {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.portfolio-tabs :deep(.n-tabs-nav) {
  background: var(--bg-elevated);
  border-radius: 12px;
  padding: 12px;
  margin-bottom: 20px;
}

.portfolio-tabs :deep(.n-tabs-tab) {
  border-radius: 8px;
  padding: 12px 24px;
  font-size: 15px;
  font-weight: 500;
  transition: all 0.3s;
  min-width: 120px;
  text-align: center;
}

.portfolio-tabs :deep(.n-tabs-tab--active) {
  background: linear-gradient(135deg, rgba(0, 212, 170, 0.15) 0%, rgba(99, 102, 241, 0.15) 100%);
  color: var(--primary);
  font-weight: 600;
  box-shadow: 0 2px 8px rgba(0, 212, 170, 0.2);
}

.portfolio-tabs :deep(.n-tabs-tab:hover:not(.n-tabs-tab--active)) {
  background: rgba(255, 255, 255, 0.05);
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

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
