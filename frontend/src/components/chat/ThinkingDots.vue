<template>
  <div class="thinking">
    <span class="think-dot" /> <span class="think-dot" /> <span class="think-dot" />
    <span class="think-text">{{ text }}</span>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ text?: string }>(), { text: '思考中…' })
</script>

<style scoped>
.thinking { display: flex; align-items: center; gap: 6px; color: var(--text-tertiary); font-size: 13px; padding: 2px 0; }
.think-text { margin-left: 2px; }
.think-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--primary); opacity: 0.4; animation: thinkpulse 1.2s infinite ease-in-out; }
.think-dot:nth-child(2) { animation-delay: 0.2s; }
.think-dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes thinkpulse { 0%,80%,100%{opacity:0.3; transform:scale(0.8)} 40%{opacity:1; transform:scale(1.1)} }
</style>
