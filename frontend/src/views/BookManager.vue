<template>
  <n-space vertical>
    <n-card title="上传书籍">
      <n-upload :max="1" :custom-request="handleUpload" accept=".pdf,.epub,.txt">
        <n-button>选择文件 (PDF/EPUB/TXT)</n-button>
      </n-upload>
      <n-space v-if="uploadedPath" style="margin-top: 16px">
        <n-tag type="success">已上传</n-tag>
        <n-button type="primary" :loading="analyzing" @click="handleAnalyze">生成投资 Agent</n-button>
      </n-space>
    </n-card>

    <n-card title="已有 Agent">
      <n-data-table :columns="columns" :data="agents" :loading="loading" />
    </n-card>
  </n-space>
</template>

<script setup lang="ts">
import { ref, h, onMounted } from 'vue'
import { NButton, useMessage } from 'naive-ui'
import { booksApi, agentsApi } from '../api'
import type { Agent } from '../types'

const message = useMessage()
const agents = ref<Agent[]>([])
const loading = ref(false)
const uploadedPath = ref('')
const analyzing = ref(false)

const columns = [
  { title: 'ID', key: 'id', width: 60 },
  { title: '名称', key: 'name' },
  { title: '类型', key: 'type' },
  { title: '描述', key: 'description' },
  {
    title: '操作', key: 'actions', width: 100,
    render: (row: Agent) => h(NButton, { size: 'small', type: 'error', onClick: () => handleDelete(row.id) }, { default: () => '删除' }),
  },
]

async function load() {
  loading.value = true
  try {
    const res = await agentsApi.list()
    agents.value = res.data
  } finally {
    loading.value = false
  }
}

async function handleUpload({ file }: any) {
  try {
    const res = await booksApi.upload(file.file)
    uploadedPath.value = res.data.path
    message.success('上传成功')
  } catch {
    message.error('上传失败')
  }
}

async function handleAnalyze() {
  analyzing.value = true
  try {
    await booksApi.generateAgent(uploadedPath.value)
    message.success('Agent 生成成功')
    uploadedPath.value = ''
    await load()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '生成失败')
  } finally {
    analyzing.value = false
  }
}

async function handleDelete(id: number) {
  await agentsApi.delete(id)
  message.success('已删除')
  await load()
}

onMounted(load)
</script>
