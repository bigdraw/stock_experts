<template>
  <n-space vertical>
    <n-card title="创建筛选脚本">
      <n-form>
        <n-form-item label="名称"><n-input v-model:value="name" placeholder="例：高ROE低PE" /></n-form-item>
        <n-form-item label="自然语言描述">
          <n-input v-model:value="nlDesc" type="textarea" placeholder="例：ROE大于15%且市盈率小于20的盈利股票" :rows="3" />
        </n-form-item>
        <n-button type="primary" :loading="generating" @click="handleGenerate">生成</n-button>
      </n-form>
    </n-card>

    <n-card title="工具库">
      <n-data-table :columns="columns" :data="filters" :loading="loading" />
    </n-card>
  </n-space>
</template>

<script setup lang="ts">
import { ref, h, onMounted } from 'vue'
import { NButton, useMessage } from 'naive-ui'
import { filtersApi } from '../api'
import type { FilterScript } from '../types'

const message = useMessage()
const filters = ref<FilterScript[]>([])
const loading = ref(false)
const generating = ref(false)
const name = ref('')
const nlDesc = ref('')

const columns = [
  { title: 'ID', key: 'id', width: 60 },
  { title: '名称', key: 'name', width: 150 },
  { title: '描述', key: 'nl_description' },
  { title: '使用次数', key: 'usage_count', width: 100 },
  {
    title: '操作', key: 'actions', width: 200,
    render: (row: FilterScript) => h(NSpace, null, {
      default: () => [
        h(NButton, { size: 'small', onClick: () => handleExecute(row.id) }, { default: () => '执行' }),
        h(NButton, { size: 'small', type: 'error', onClick: () => handleDelete(row.id) }, { default: () => '删除' }),
      ],
    }),
  },
]

import { NSpace } from 'naive-ui'

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
  generating.value = true
  try {
    await filtersApi.generate(name.value, nlDesc.value)
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
