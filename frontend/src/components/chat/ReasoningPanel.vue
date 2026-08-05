<template>
  <div class="reasoning-panel">
    <div class="reasoning-head" @click="open = !open">
      <span>🧠 思考链 · {{ reasoning.length }} 字{{ streaming && !hasContent ? ' · 思考中…' : '' }}</span>
      <span class="reasoning-toggle">{{ open ? '收起 ▲' : '展开 ▼' }}</span>
    </div>
    <div v-if="open" class="reasoning-body">{{ reasoning }}<span v-if="streaming && !hasContent" class="cursor">▋</span></div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  reasoning: string
  streaming?: boolean
  hasContent?: boolean
}>()

const open = ref(true)  // 默认展开（思考链可见）
</script>

<style scoped>
.reasoning-panel {
  border-left: 2px solid var(--border-medium); margin: 0 0 10px 4px; padding: 4px 0;
  background: rgba(100, 116, 139, 0.06); border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}
.reasoning-head {
  display: flex; justify-content: space-between; align-items: center; cursor: pointer;
  padding: 4px 10px; font-size: 12px; color: var(--text-tertiary); font-weight: 500;
}
.reasoning-head:hover { color: var(--text-secondary); }
.reasoning-toggle { font-size: 11px; }
.reasoning-body {
  margin: 0 10px 6px; padding-top: 6px; border-top: 1px dashed var(--border-subtle);
  color: var(--text-tertiary); font-size: 13px; line-height: 1.55; white-space: pre-wrap;
  max-height: 360px; overflow-y: auto; word-wrap: break-word;
}
.cursor { color: var(--primary); animation: blink 1s infinite; }
@keyframes blink { 0%,50%{opacity:1} 51%,100%{opacity:0} }
</style>
