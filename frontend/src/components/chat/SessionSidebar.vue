<template>
  <div class="session-sidebar">
    <div class="sidebar-top">
      <n-button v-if="!manageMode" block type="primary" size="small" @click="handleNewSession">+ 新对话</n-button>
      <n-space v-else :size="6" class="manage-bar">
        <n-button size="small" type="error" :disabled="!checked.size" @click="batchDelete">删除选中({{ checked.size }})</n-button>
        <n-button size="small" quaternary @click="exitManage">取消</n-button>
      </n-space>
    </div>
    <div class="search-row">
      <n-input v-model:value="searchText" placeholder="搜索…" size="small" clearable class="search" />
      <n-button v-if="!manageMode" size="tiny" quaternary class="manage-btn" @click="enterManage">管理</n-button>
    </div>
    <div class="session-list">
      <div
        v-for="s in filteredSessions"
        :key="s.id"
        :class="['session-item', { active: !manageMode && s.id === chatStore.currentSessionId, manage: manageMode, checked: manageMode && checked.has(s.id) }]"
        @click="onItemClick(s)"
      >
        <!-- 管理模式：整行可点切换勾选（大点击区），checkbox 纯显示——避免 checkbox 的
             @update:checked 与行 @click 双触发互相抵消导致"点不中" -->
        <n-checkbox v-if="manageMode" :checked="checked.has(s.id)" class="session-check" />
        <span class="session-title">{{ s.title }}</span>
        <n-tag v-if="s.type === 'debate'" size="tiny" type="warning" round class="type-tag">辩论</n-tag>
      </div>
      <div v-if="filteredSessions.length === 0" class="empty">暂无会话</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { NButton, NInput, NTag, NSpace, NCheckbox, useMessage } from 'naive-ui'
import { useChatStore } from '../../stores/chat'
import type { ChatSessionData } from '../../stores/chat'

const chatStore = useChatStore()
const message = useMessage()
const searchText = ref('')
const manageMode = ref(false)
// 用 reactive Set 维持勾选态（collection reactivity）
const checked = reactive(new Set<number>())

const filteredSessions = computed(() => {
  if (!searchText.value) return chatStore.sessions
  return chatStore.sessions.filter(s => s.title.toLowerCase().includes(searchText.value.toLowerCase()))
})

function handleNewSession() { chatStore.createSession() }

function onItemClick(s: ChatSessionData) {
  if (manageMode.value) {
    toggleCheck(s.id, !checked.has(s.id))
    return
  }
  // debate 与 chat 会话都在 ChatHome 内联渲染（多 agent 气泡），不再跳 /debate 回看页
  chatStore.selectSession(s.id)
}

function enterManage() {
  manageMode.value = true
  checked.clear()
}
function exitManage() {
  manageMode.value = false
  checked.clear()
}
function toggleCheck(id: number, v: boolean) {
  if (v) checked.add(id); else checked.delete(id)
}
async function batchDelete() {
  if (!checked.size) return
  const ids = [...checked]
  await chatStore.deleteSessions(ids)
  message.success(`已删除 ${ids.length} 个会话`)
  checked.clear()
  if (chatStore.sessions.length === 0) manageMode.value = false
}
</script>

<style scoped>
.session-sidebar {
  display: flex; flex-direction: column; height: 100%; width: 260px; flex-shrink: 0;
  background: var(--bg-elevated); border-right: 1px solid var(--border-subtle);
}
.sidebar-top { padding: 12px; }
.manage-bar { width: 100%; }
.search-row { display: flex; align-items: center; gap: 4px; padding: 0 12px 8px; }
.search { flex: 1; }
.manage-btn { flex-shrink: 0; }
.session-list { flex: 1; overflow-y: auto; padding: 0 8px 8px; }
.session-item {
  padding: 8px 12px 8px 10px; border-radius: var(--radius-sm); cursor: pointer;
  transition: all var(--transition); margin-bottom: 2px; position: relative;
  display: flex; align-items: center; gap: 6px;
  border-left: 3px solid transparent;
}
.session-item:hover { background: var(--primary-tint); transform: translateX(2px); }
.session-item:hover .session-title { color: var(--primary); }
.session-item.active {
  background: var(--primary-tint-strong); border-left: 3px solid var(--primary);
}
.session-item.active .session-title { color: var(--primary); font-weight: var(--fw-bold); }
.session-item.manage { cursor: default; }
.session-item.manage:hover { background: var(--bg-surface); transform: none; }
.session-item.manage:hover .session-title { color: var(--text-secondary); }
.session-item.checked { background: var(--primary-tint-strong); border-left: 3px solid var(--accent); }
.session-item.checked:hover { background: var(--primary-glow); }
.session-check { flex-shrink: 0; }
.session-title {
  font-size: 14px; color: var(--text-secondary); overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; flex: 1; min-width: 0;
  transition: color var(--transition), font-weight var(--transition);
}
.type-tag { flex-shrink: 0; }
.empty { text-align: center; padding: 40px 0; color: var(--text-tertiary); font-size: var(--fs-label); }
</style>
