<template>
  <div class="session-sidebar">
    <div class="sidebar-header">
      <n-button block type="primary" size="small" @click="handleNewSession">
        <template #icon><n-icon><AddOutline /></n-icon></template>
        新对话
      </n-button>
    </div>
    <n-input v-model:value="searchText" placeholder="搜索会话…" size="small" clearable class="search-input" />
    <div class="session-list">
      <div
        v-for="s in filteredSessions"
        :key="s.id"
        :class="['session-item', { active: s.id === chatStore.currentSessionId }]"
        @click="chatStore.selectSession(s.id)"
        @contextmenu.prevent="showMenu($event, s)"
      >
        <n-icon v-if="s.pinned" size="14" color="#f59e0b" style="margin-right: 4px;"><PinOutline /></n-icon>
        <span class="session-title">{{ s.title }}</span>
        <span v-if="s.last_message_at" class="session-time">{{ formatTime(s.last_message_at) }}</span>
      </div>
      <div v-if="filteredSessions.length === 0" class="empty-sessions">暂无会话</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { NIcon, useDialog } from 'naive-ui'
import { AddOutline, PinOutline } from '@vicons/ionicons5'
import { useChatStore } from '../../stores/chat'

const chatStore = useChatStore()
const dialog = useDialog()
const searchText = ref('')

const filteredSessions = computed(() => {
  if (!searchText.value) return chatStore.sessions
  return chatStore.sessions.filter(s => s.title.toLowerCase().includes(searchText.value.toLowerCase()))
})

function handleNewSession() {
  chatStore.createSession()
}

function showMenu(e: MouseEvent, session: any) {
  // 右键菜单：重命名/删除/置顶
  dialog.warning({
    title: '会话操作',
    content: `"${session.title}" — 删除？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: () => chatStore.deleteSession(session.id),
  })
}

function formatTime(s: string): string {
  if (!s) return ''
  const d = new Date(s)
  const now = new Date()
  if (d.toDateString() === now.toDateString()) return d.toTimeString().slice(0, 5)
  return `${d.getMonth() + 1}/${d.getDate()}`
}
</script>

<style scoped>
.session-sidebar { display: flex; flex-direction: column; height: 100%; }
.sidebar-header { padding: 12px; }
.search-input { margin: 0 12px 8px; width: calc(100% - 24px); }
.session-list { flex: 1; overflow-y: auto; padding: 0 8px 8px; }
.session-item {
  display: flex; align-items: center; gap: 4px;
  padding: 8px 12px; border-radius: 8px; cursor: pointer;
  transition: all 0.2s; margin-bottom: 2px;
}
.session-item:hover { background: rgba(99,102,241,0.08); }
.session-item.active { background: rgba(99,102,241,0.15); }
.session-title { flex: 1; font-size: 13px; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.session-time { font-size: 11px; color: var(--text-tertiary); }
.empty-sessions { text-align: center; padding: 40px 0; color: var(--text-tertiary); font-size: 13px; }
</style>
