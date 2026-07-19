<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-left">
        <n-icon :size="32" color="#10b981">
          <BookOutline />
        </n-icon>
        <h2 class="page-title gradient-text">书籍管理</h2>
      </div>
    </div>

    <n-card title="上传书籍" class="action-card">
      <template #header-extra>
        <n-icon :size="20" color="#00d4aa">
          <CloudUploadOutline />
        </n-icon>
      </template>
      <n-upload 
        :max="1" 
        :custom-request="handleUpload" 
        accept=".pdf,.epub,.txt"
        class="upload-area"
      >
        <n-button size="large" class="upload-button">
          <template #icon>
            <n-icon :size="18">
              <DocumentOutline />
            </n-icon>
          </template>
          选择文件 (PDF/EPUB/TXT)
        </n-button>
      </n-upload>
      <div v-if="uploadedPath" class="upload-status">
        <n-tag type="success" round size="large">
          <template #icon>
            <n-icon :size="16">
              <CheckmarkCircleOutline />
            </n-icon>
          </template>
          已上传
        </n-tag>
        <n-button type="primary" :loading="analyzing" @click="handleAnalyze" size="large" class="action-button">
          <template #icon>
            <n-icon :size="18">
              <SparklesOutline />
            </n-icon>
          </template>
          生成投资 Agent
        </n-button>
      </div>
    </n-card>

    <n-card title="已有 Agent" class="data-card">
      <template #header-extra>
        <n-icon :size="20" color="#6366f1">
          <PeopleOutline />
        </n-icon>
      </template>
      <n-data-table 
        :columns="columns" 
        :data="agents" 
        :loading="loading"
        :bordered="false"
      />
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, h, onMounted } from 'vue'
import { NButton, NTag, useMessage } from 'naive-ui'
import { 
  BookOutline, 
  CloudUploadOutline, 
  DocumentOutline,
  CheckmarkCircleOutline,
  SparklesOutline,
  PeopleOutline,
  TrashOutline
} from '@vicons/ionicons5'
import { booksApi, agentsApi } from '../api'
import type { Agent } from '../types'

const message = useMessage()
const agents = ref<Agent[]>([])
const loading = ref(false)
const uploadedPath = ref('')
const analyzing = ref(false)

const columns = [
  { 
    title: 'ID', 
    key: 'id', 
    width: 80,
    render: (row: Agent) => h(NTag, { 
      size: 'small',
      type: 'default',
      round: true
    }, { default: () => `#${row.id}` })
  },
  { 
    title: '名称', 
    key: 'name',
    render: (row: Agent) => h('span', { 
      style: 'font-weight: 600; color: var(--text-primary);'
    }, row.name)
  },
  { 
    title: '类型', 
    key: 'type',
    render: (row: Agent) => h(NTag, { 
      size: 'small',
      type: row.type === 'book_generated' ? 'success' : 'info',
      round: true
    }, { default: () => row.type === 'book_generated' ? '书籍生成' : '手动创建' })
  },
  { 
    title: '描述', 
    key: 'description',
    render: (row: Agent) => h('span', { 
      style: 'color: var(--text-secondary); font-size: 13px;'
    }, row.description || '-')
  },
  {
    title: '操作', 
    key: 'actions', 
    width: 120,
    render: (row: Agent) => h(NButton, { 
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

.upload-area {
  margin-bottom: 16px;
}

.upload-button {
  background: rgba(30, 41, 59, 0.6) !important;
  border: 2px dashed var(--border-medium) !important;
  border-radius: 12px !important;
  padding: 24px 48px !important;
  font-weight: 600 !important;
  transition: all 0.3s !important;
}

.upload-button:hover {
  border-color: var(--primary) !important;
  background: rgba(0, 212, 170, 0.05) !important;
  box-shadow: 0 0 20px rgba(0, 212, 170, 0.2) !important;
}

.upload-status {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px;
  background: rgba(30, 41, 59, 0.4);
  border-radius: 8px;
  border: 1px solid var(--border-subtle);
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
