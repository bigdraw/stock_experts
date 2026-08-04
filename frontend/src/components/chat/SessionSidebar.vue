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
        @click="handleSelect(s)"
      >
        <span class="session-title">{{ s.title }}</span>
        <n-tag v-if="s.type === 'debate'" size="tiny" type="warning" round class="type-tag">辩论</n-tag>
      </div>
      <div v-if="filteredSessions.length === 0" class="empty">暂无会话</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NInput, NTag } from 'naive-ui'
import { useChatStore } from '../../stores/chat'
import type { ChatSessionData } from '../../stores/chat'

const chatStore = useChatStore()
const router = useRouter()
const searchText = ref('')

const filteredSessions = computed(() => {
  if (!searchText.value) return chatStore.sessions
  return chatStore.sessions.filter(s => s.title.toLowerCase().includes(searchText.value.toLowerCase()))
})

function handleNewSession() { chatStore.createSession() }

// debate 会话 → 跳辩论页回看；chat 会话 → 原地选中加载
function handleSelect(s: ChatSessionData) {
  if (s.type === 'debate') {
    router.push({ name: 'DebateCreate', query: { session: String(s.id) } })
  } else {
    chatStore.selectSession(s.id)
  }
}
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
.type-tag { margin-left: 6px; flex-shrink: 0; }
.session-item { align-items: center; }
.empty { text-align: center; padding: 40px 0; color: var(--text-tertiary); font-size: 13px; }
</style>
