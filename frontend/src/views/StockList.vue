<template>
  <n-space vertical>
    <n-input v-model:value="search" placeholder="搜索股票代码或名称..." clearable @update:value="handleSearch" />
    <n-data-table :columns="columns" :data="stocks" :loading="loading" :pagination="{ pageSize: 50 }" />
  </n-space>
</template>

<script setup lang="ts">
import { ref, h, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { NButton } from 'naive-ui'
import { stocksApi } from '../api'
import type { Stock } from '../types'

const router = useRouter()
const stocks = ref<Stock[]>([])
const loading = ref(false)
const search = ref('')

const columns = [
  { title: '代码', key: 'code', width: 100 },
  { title: '名称', key: 'name', width: 120 },
  { title: '市场', key: 'market', width: 60 },
  { title: '行业', key: 'industry', width: 120 },
  {
    title: '操作', key: 'actions', width: 200,
    render: (row: Stock) => h(NButton, { size: 'small', onClick: () => router.push(`/stocks/${row.code}`) }, { default: () => '详情' }),
  },
]

async function loadStocks() {
  loading.value = true
  try {
    const res = await stocksApi.list({ search: search.value || undefined, limit: 500 })
    stocks.value = res.data
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  loadStocks()
}

onMounted(loadStocks)
</script>
