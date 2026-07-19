<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-left">
        <n-icon :size="32" color="#00d4aa">
          <BriefcaseOutline />
        </n-icon>
        <h2 class="page-title gradient-text">投资组合</h2>
      </div>
      <n-button type="primary" @click="showCreate = true" class="create-button">
        <template #icon>
          <n-icon :size="18">
            <AddOutline />
          </n-icon>
        </template>
        创建组合
      </n-button>
    </div>

    <n-grid :cols="3" :x-gap="20" :y-gap="20" v-if="portfolios.length">
      <n-gi v-for="p in portfolios" :key="p.id">
        <n-card 
          :title="p.name" 
          hoverable 
          @click="$router.push(`/portfolios/${p.id}`)"
          class="portfolio-card"
        >
          <template #header-extra>
            <n-icon :size="20" color="#6366f1">
              <TrendingUpOutline />
            </n-icon>
          </template>
          <p class="portfolio-desc">{{ p.description || '无描述' }}</p>
          <div class="portfolio-meta">
            <n-tag size="small" type="info" round>
              <template #icon>
                <n-icon :size="14">
                  <TimeOutline />
                </n-icon>
              </template>
              {{ formatDate(p.created_at) }}
            </n-tag>
          </div>
          <template #action>
            <n-space justify="space-between">
              <n-button size="small" type="primary" ghost @click.stop="$router.push(`/portfolios/${p.id}`)">
                <template #icon>
                  <n-icon :size="14">
                    <EyeOutline />
                  </n-icon>
                </template>
                查看
              </n-button>
              <n-button size="small" type="error" ghost @click.stop="handleDelete(p.id)">
                <template #icon>
                  <n-icon :size="14">
                    <TrashOutline />
                  </n-icon>
                </template>
                删除
              </n-button>
            </n-space>
          </template>
        </n-card>
      </n-gi>
    </n-grid>

    <n-empty v-if="!portfolios.length" description="暂无投资组合" class="empty-state">
      <template #extra>
        <n-button type="primary" @click="showCreate = true">
          <template #icon>
            <n-icon :size="18">
              <AddOutline />
            </n-icon>
          </template>
          创建第一个组合
        </n-button>
      </template>
    </n-empty>

    <n-modal v-model:show="showCreate" preset="dialog" title="创建组合" class="create-modal">
      <template #header>
        <div class="modal-header">
          <n-icon :size="24" color="#00d4aa">
            <BriefcaseOutline />
          </n-icon>
          <span class="gradient-text">创建投资组合</span>
        </div>
      </template>
      <n-form class="create-form">
        <n-form-item label="组合名称">
          <n-input v-model:value="newName" placeholder="请输入组合名称" />
        </n-form-item>
        <n-form-item label="组合描述">
          <n-input v-model:value="newDesc" type="textarea" placeholder="请输入组合描述（可选）" :rows="3" />
        </n-form-item>
      </n-form>
      <template #action>
        <n-button @click="showCreate = false">取消</n-button>
        <n-button type="primary" @click="handleCreate" class="create-button">创建</n-button>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useMessage } from 'naive-ui'
import { 
  BriefcaseOutline, 
  AddOutline, 
  TrendingUpOutline,
  TimeOutline,
  EyeOutline,
  TrashOutline
} from '@vicons/ionicons5'
import { portfoliosApi } from '../api'
import type { Portfolio } from '../types'

const message = useMessage()
const portfolios = ref<Portfolio[]>([])
const showCreate = ref(false)
const newName = ref('')
const newDesc = ref('')

function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

async function load() {
  const res = await portfoliosApi.list()
  portfolios.value = res.data
}

async function handleCreate() {
  if (!newName.value.trim()) {
    message.warning('请输入组合名称')
    return
  }
  await portfoliosApi.create(newName.value.trim(), newDesc.value)
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

.create-button {
  background: linear-gradient(135deg, #00d4aa 0%, #6366f1 100%) !important;
  border: none !important;
  font-weight: 600 !important;
  transition: all 0.3s !important;
}

.create-button:hover {
  box-shadow: 0 8px 24px rgba(0, 212, 170, 0.4) !important;
  transform: translateY(-2px);
}

.portfolio-card {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 12px !important;
  transition: all 0.3s !important;
  cursor: pointer;
  position: relative;
  overflow: hidden;
}

.portfolio-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, #00d4aa 0%, #6366f1 100%);
  opacity: 0;
  transition: opacity 0.3s;
}

.portfolio-card:hover::before {
  opacity: 1;
}

.portfolio-card:hover {
  border-color: var(--primary) !important;
  box-shadow: 0 8px 32px rgba(0, 212, 170, 0.2) !important;
  transform: translateY(-4px);
}

.portfolio-card :deep(.n-card-header) {
  border-bottom: 1px solid var(--border-subtle);
}

.portfolio-card :deep(.n-card-header__main) {
  font-weight: 600;
  font-size: 18px;
  color: var(--text-primary);
}

.portfolio-desc {
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.6;
  margin: 0 0 16px 0;
  min-height: 44px;
}

.portfolio-meta {
  margin-bottom: 16px;
}

.portfolio-card :deep(.n-card__action) {
  border-top: 1px solid var(--border-subtle);
  padding: 12px 16px;
  background: rgba(30, 41, 59, 0.4);
}

.empty-state {
  margin-top: 80px;
}

.empty-state :deep(.n-empty__description) {
  color: var(--text-tertiary);
  font-size: 16px;
  margin-bottom: 24px;
}

.create-modal :deep(.n-card) {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border-medium) !important;
  border-radius: 16px !important;
}

.modal-header {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 20px;
  font-weight: 700;
}

.create-form :deep(.n-form-item-label) {
  font-weight: 600;
  color: var(--text-secondary);
}

.create-form :deep(.n-input) {
  background: rgba(30, 41, 59, 0.6) !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 8px !important;
  transition: all 0.3s !important;
}

.create-form :deep(.n-input:hover) {
  border-color: var(--primary) !important;
  background: rgba(30, 41, 59, 0.8) !important;
}

.create-form :deep(.n-input--focus) {
  border-color: var(--primary) !important;
  box-shadow: 0 0 0 2px rgba(0, 212, 170, 0.15) !important;
  background: rgba(30, 41, 59, 0.9) !important;
}
</style>
