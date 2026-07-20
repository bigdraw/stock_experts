<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-left">
        <n-icon :size="32" color="#10b981">
          <BookOutline />
        </n-icon>
        <h2 class="page-title gradient-text">Agent构建</h2>
      </div>
    </div>

    <!-- 构建 Agent（二合一：文本输入 + 拖拽多文件）idea11 -->
    <n-card class="action-card">
      <template #header>
        <span style="font-weight: 600; color: var(--text-primary);">构建 Agent</span>
      </template>
      <template #header-extra>
        <n-icon :size="20" color="#00d4aa">
          <SparklesOutline />
        </n-icon>
      </template>
      <n-space vertical :size="12">
        <n-input v-model:value="agentName" placeholder="Agent 名称，如：稳健价值型" />

        <!-- 二合一输入区：textarea + 拖拽 drop zone 叠加 -->
        <div
          class="combined-input-zone"
          :class="{ dragover }"
          @drop.prevent="handleDrop"
          @dragover.prevent="dragover = true"
          @dragleave.prevent="dragover = false"
        >
          <n-input
            v-model:value="textContent"
            type="textarea"
            :autosize="{ minRows: 6, maxRows: 18 }"
            placeholder="粘贴投资理念 / 策略公式 / 一段投资逻辑。&#10;也可以把 TXT / PDF / EPUB 文件直接拖到这里（支持多文件）。"
            style="background: transparent;"
          />
          <div v-if="dragover" class="drop-overlay">
            <n-icon :size="32" color="#00d4aa"><CloudUploadOutline /></n-icon>
            <span>松开以添加文件</span>
          </div>
        </div>

        <div class="drop-hint">支持拖拽多个文件 · TXT 自动读取内容填入文本框 · PDF/EPUB 上传后服务端解析</div>

        <!-- 已上传文件列表 -->
        <n-space v-if="uploadedFiles.length" :size="8">
          <n-tag v-for="f in uploadedFiles" :key="f.name" type="success" round size="small">
            {{ f.name }}
          </n-tag>
        </n-space>

        <n-button
          type="primary"
          size="large"
          :loading="generating"
          :disabled="!agentName || (!textContent && !uploadedFiles.length)"
          @click="handleGenerate"
        >
          <template #icon>
            <n-icon :size="18"><SparklesOutline /></n-icon>
          </template>
          生成 Agent
        </n-button>
      </n-space>
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
import { NButton, NTag, NIcon, useMessage } from 'naive-ui'
import {
  BookOutline,
  CloudUploadOutline,
  SparklesOutline,
  PeopleOutline,
  TrashOutline
} from '@vicons/ionicons5'
import { booksApi, agentsApi } from '../api'
import type { Agent } from '../types'

const message = useMessage()
const agents = ref<Agent[]>([])
const loading = ref(false)
const agentName = ref('')
const textContent = ref('')
const uploadedFiles = ref<{ name: string; path: string }[]>([])
const dragover = ref(false)
const generating = ref(false)

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

async function handleDrop(e: DragEvent) {
  dragover.value = false
  const files = Array.from(e.dataTransfer?.files || [])
  for (const file of files) {
    const ext = file.name.split('.').pop()?.toLowerCase()
    if (ext === 'txt') {
      // TXT: 客户端直接读内容填入文本框
      const text = await file.text()
      textContent.value = textContent.value
        ? `${textContent.value}\n\n--- ${file.name} ---\n${text}`
        : text
      message.success(`已读取 ${file.name} 内容`)
    } else if (ext === 'pdf' || ext === 'epub') {
      // PDF/EPUB: 上传到服务端解析
      try {
        const res = await booksApi.upload(file)
        uploadedFiles.value.push({ name: file.name, path: res.data.path })
        message.success(`已上传 ${file.name}`)
      } catch {
        message.error(`上传 ${file.name} 失败`)
      }
    } else {
      message.warning(`不支持的格式: ${file.name}（仅 TXT/PDF/EPUB）`)
    }
  }
}

async function handleGenerate() {
  generating.value = true
  try {
    let count = 0
    // 1. 文本内容 → generate-agent-from-text
    if (textContent.value.trim()) {
      await booksApi.generateAgentFromText(agentName.value, textContent.value)
      count++
    }
    // 2. 上传的文件 → generate-agent per file
    for (const f of uploadedFiles.value) {
      await booksApi.generateAgent(f.path)
      count++
    }
    if (count > 0) {
      message.success(`生成 ${count} 个 Agent 成功`)
      agentName.value = ''
      textContent.value = ''
      uploadedFiles.value = []
      await load()
    } else {
      message.warning('请输入文本或拖入文件')
    }
  } catch (e: any) {
    message.error(e.response?.data?.detail || '生成失败')
  } finally {
    generating.value = false
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

/* 二合一输入区：textarea + drop zone */
.combined-input-zone {
  position: relative;
  border: 2px dashed var(--border-subtle);
  border-radius: 10px;
  transition: all 0.2s;
}
.combined-input-zone.dragover {
  border-color: #00d4aa;
  background: rgba(0, 212, 170, 0.08);
}
.combined-input-zone :deep(.n-input) {
  --n-border: 0 !important;
}
.drop-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: rgba(0, 212, 170, 0.12);
  border-radius: 10px;
  color: #00d4aa;
  font-weight: 600;
  pointer-events: none;
}
.drop-hint {
  font-size: 12px;
  color: var(--text-tertiary);
  text-align: center;
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
