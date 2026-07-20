<template>
  <div class="markdown-body" v-html="rendered"></div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'

const props = defineProps<{ content: string }>()

const md = new MarkdownIt({
  html: false,
  linkify: true,
  highlight(str: string, lang: string) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return `<pre class="hljs"><code>${hljs.highlight(str, { language: lang }).value}</code></pre>`
      } catch { /* fallback */ }
    }
    return `<pre class="hljs"><code>${md.utils.escapeHtml(str)}</code></pre>`
  },
})

const rendered = computed(() => md.render(props.content || ''))
</script>

<style scoped>
.markdown-body :deep(p) { margin: 0.5em 0; line-height: 1.7; }
.markdown-body :deep(ul), .markdown-body :deep(ol) { padding-left: 1.5em; }
.markdown-body :deep(code) { background: rgba(99,102,241,0.15); padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }
.markdown-body :deep(.hljs) { border-radius: 8px; padding: 12px 16px; overflow-x: auto; font-size: 0.85em; background: rgba(15,23,42,0.6); }
.markdown-body :deep(blockquote) { border-left: 3px solid var(--border-medium); padding-left: 1em; color: var(--text-secondary); margin: 0.5em 0; }
.markdown-body :deep(a) { color: #6366f1; }
.markdown-body :deep(table) { border-collapse: collapse; width: 100%; margin: 0.5em 0; }
.markdown-body :deep(th), .markdown-body :deep(td) { border: 1px solid var(--border-subtle); padding: 6px 10px; font-size: 0.9em; }
</style>
