<template>
  <div class="thinking">
    <span class="bolt">⚡</span> <span class="bolt">⚡</span> <span class="bolt">⚡</span>
    <span class="think-text">{{ text }}</span>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ text?: string }>(), { text: '小雷思考中…' })
</script>

<style scoped>
.thinking { display: flex; align-items: center; gap: 4px; color: var(--text-tertiary); font-size: 13px; padding: 2px 0; }
.think-text { margin-left: 4px; }
.bolt { font-size: 14px; color: var(--primary); opacity: 0.4; animation: boltPulse 1.2s infinite ease-in-out; display: inline-block; }
.bolt:nth-child(2) { animation-delay: 0.2s; }
.bolt:nth-child(3) { animation-delay: 0.4s; }
@keyframes boltPulse { 0%,100%{opacity:0.3; transform:scale(0.85)} 50%{opacity:1; transform:scale(1.15)} }

@media (prefers-reduced-motion: reduce) {
  .bolt { animation: none; opacity: 0.6; }
}
</style>
