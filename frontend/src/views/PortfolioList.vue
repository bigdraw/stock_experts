<template>
  <n-space vertical>
    <n-space justify="space-between">
      <n-h2>投资组合</n-h2>
      <n-button type="primary" @click="showCreate = true">创建组合</n-button>
    </n-space>
    <n-grid :cols="3" :x-gap="16" :y-gap="16">
      <n-gi v-for="p in portfolios" :key="p.id">
        <n-card :title="p.name" hoverable @click="$router.push(`/portfolios/${p.id}`)">
          <p>{{ p.description || '无描述' }}</p>
          <template #action>
            <n-space>
              <n-button size="small" @click.stop="$router.push(`/portfolios/${p.id}`)">查看</n-button>
              <n-button size="small" type="error" @click.stop="handleDelete(p.id)">删除</n-button>
            </n-space>
          </template>
        </n-card>
      </n-gi>
    </n-grid>
    <n-empty v-if="!portfolios.length" description="暂无投资组合" />

    <n-modal v-model:show="showCreate" preset="dialog" title="创建组合">
      <n-form>
        <n-form-item label="名称"><n-input v-model:value="newName" /></n-form-item>
        <n-form-item label="描述"><n-input v-model:value="newDesc" type="textarea" /></n-form-item>
      </n-form>
      <template #action>
        <n-button @click="showCreate = false">取消</n-button>
        <n-button type="primary" @click="handleCreate">创建</n-button>
      </template>
    </n-modal>
  </n-space>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useMessage } from 'naive-ui'
import { portfoliosApi } from '../api'
import type { Portfolio } from '../types'

const message = useMessage()
const portfolios = ref<Portfolio[]>([])
const showCreate = ref(false)
const newName = ref('')
const newDesc = ref('')

async function load() {
  const res = await portfoliosApi.list()
  portfolios.value = res.data
}

async function handleCreate() {
  await portfoliosApi.create(newName.value, newDesc.value)
  showCreate.value = false
  newName.value = ''
  newDesc.value = ''
  message.success('组合创建成功')
  await load()
}

async function handleDelete(id: number) {
  await portfoliosApi.delete(id)
  message.success('组合已删除')
  await load()
}

onMounted(load)
</script>
