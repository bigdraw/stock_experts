<template>
  <n-space vertical>
    <n-card title="创建告警">
      <n-form inline>
        <n-form-item label="名称"><n-input v-model:value="name" placeholder="例：ROE告警" /></n-form-item>
        <n-form-item label="条件描述"><n-input v-model:value="condition" placeholder="例：ROE大于20%" /></n-form-item>
        <n-button type="primary" @click="handleCreate">创建</n-button>
      </n-form>
    </n-card>
    <n-card title="告警列表">
      <n-data-table :columns="columns" :data="alerts" :loading="loading" />
    </n-card>
  </n-space>
</template>

<script setup lang="ts">
import { ref, h, onMounted } from 'vue'
import { NButton, NSwitch, useMessage } from 'naive-ui'
import { alertsApi } from '../api'
import type { Alert } from '../types'

const message = useMessage()
const alerts = ref<Alert[]>([])
const loading = ref(false)
const name = ref('')
const condition = ref('')

const columns = [
  { title: '名称', key: 'name' },
  { title: '条件', key: 'nl_condition' },
  { title: '状态', key: 'is_active', render: (row: Alert) => h(NSwitch, { value: row.is_active, onUpdateValue: () => handleToggle(row.id) }) },
  {
    title: '操作', key: 'actions',
    render: (row: Alert) => h(NButton, { size: 'small', type: 'error', onClick: () => handleDelete(row.id) }, { default: () => '删除' }),
  },
]

async function load() {
  loading.value = true
  try {
    const res = await alertsApi.list()
    alerts.value = res.data
  } finally {
    loading.value = false
  }
}

async function handleCreate() {
  if (!name.value.trim()) {
    message.warning('请输入告警名称')
    return
  }
  if (!condition.value.trim()) {
    message.warning('请输入告警条件')
    return
  }
  await alertsApi.create(name.value.trim(), condition.value.trim())
  message.success('告警创建成功')
  name.value = ''
  condition.value = ''
  await load()
}

async function handleToggle(id: number) {
  await alertsApi.toggle(id)
  await load()
}

async function handleDelete(id: number) {
  await alertsApi.delete(id)
  message.success('已删除')
  await load()
}

onMounted(load)
</script>
