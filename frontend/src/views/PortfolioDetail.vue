<template>
  <n-space vertical v-if="detail">
    <n-h2>{{ detail.name }}</n-h2>
    <n-space>
      <n-input v-model:value="addCode" placeholder="股票代码" style="width: 150px" />
      <n-input-number v-model:value="addShares" placeholder="数量" style="width: 120px" />
      <n-button type="primary" @click="handleAdd">添加股票</n-button>
    </n-space>
    <n-data-table :columns="columns" :data="detail.holdings" />
  </n-space>
</template>

<script setup lang="ts">
import { ref, h, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { NButton, useMessage } from 'naive-ui'
import { portfoliosApi } from '../api'
import type { PortfolioDetail } from '../types'

const route = useRoute()
const message = useMessage()
const id = Number(route.params.id)
const detail = ref<PortfolioDetail | null>(null)
const addCode = ref('')
const addShares = ref(100)

const columns = [
  { title: '代码', key: 'stock_code' },
  { title: '名称', key: 'stock_name' },
  { title: '数量', key: 'shares' },
  { title: '成本', key: 'avg_cost' },
  {
    title: '操作', key: 'actions',
    render: (row: any) => h(NButton, { size: 'small', type: 'error', onClick: () => handleRemove(row.stock_code) }, { default: () => '移除' }),
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

async function handleRemove(code: string) {
  await portfoliosApi.removeStock(id, code)
  message.success('已移除')
  await load()
}

onMounted(load)
</script>
