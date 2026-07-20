<template>
  <div class="session-sidebar">
    <div class="sidebar-top">
      <n-button block type="primary" size="small" @click="handleNewSession">+ 新对话</n-button>
    </div>
    <n-input v-model:value="searchText" placeholder="搜索…" size="small" clearable class="search" />
    <div class="session-list">
      <div
        v-for="s in filteredSessions"
        :key="s.id"
        :class="['session-item', { active: s.id === chatStore.currentSessionId }]"
        @click="chatStore.selectSession(s.id)"
      >
        <span class="session-title">{{ s.title }}</span>
      </div>
      <div v-if="filteredSessions.length === 0" class="empty">暂无会话</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { NButton, NInput, useDialog } from 'naive-ui'
import { useChatStore } from '../../stores/chat'

const chatStore = useChatStore()
const dialog = useDialog()
const searchText = ref('')

const filteredSessions = computed(() => {
  if (!searchText.value) return chatStore.sessions
  return chatStore.sessions.filter(s => s.title.toLowerCase().includes(searchText.value.toLowerCase()))
})

function handleNewSession() { chatStore.createSession() }
</script>

<style scoped>
.session-sidebar {
  display: flex; flex-direction: column; height: 100%; width: 260px; flex-shrink: 0;
  background: var(--bg-elevated); border-right: 1px solid var(--border-subtle);
}
.sidebar-top { padding: 12px; }
.search { margin: 0 12px 8px; width: calc(100% - 24px); }
.session-list { flex: 1; overflow-y: auto; padding: 0 8px 8px; }
.session-item {
  padding: 8px 12px; border-radius: var(--radius-sm); cursor: pointer;
  transition: background var(--transition); margin-bottom: 2px;
}
.session-item:hover { background: var(--bg-surface); }
.session-item.active { background: var(--bg-surface); }
.session-title {
  font-size: 14px; color: var(--text-secondary); overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; display: block;
}
.empty { text-align: center; padding: 40px 0; color: var(--text-tertiary); font-size: 13px; }
</style>
