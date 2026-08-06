<template>
  <div class="markdown-body" v-html="rendered"></div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import DOMPurify from 'dompurify'

const props = defineProps<{ content: string }>()

const md: MarkdownIt = new MarkdownIt({
  html: false,
  linkify: true,
  highlight(str: string, lang: string): string {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return `<pre class="hljs"><code>${hljs.highlight(str, { language: lang }).value}</code></pre>`
      } catch { /* fallback */ }
    }
    return `<pre class="hljs"><code>${md.utils.escapeHtml(str)}</code></pre>`
  },
})

// Agent output is untrusted LLM content (prompt-injectable). markdown-it
// html:false already escapes raw HTML, but sanitize the rendered HTML too so
// javascript:/data: URIs, on* handlers, <script>/<iframe>/<style> injected via
// highlight.js output or linkify can't reach the v-html DOM (ISSUE-026).
const rendered = computed(() =>
  DOMPurify.sanitize(md.render(props.content || ''), {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ['style', 'iframe', 'form', 'object', 'embed'],
    FORBID_ATTR: ['style'],
  })
)
</script>

<style scoped>
.markdown-body :deep(p) { margin: 0.5em 0; line-height: 1.7; }
/* 标题：覆盖浏览器默认（h1=2em+大 margin 在气泡里过大、与 agent 名挤） */
.markdown-body :deep(h1) { font-size: 1.3em; margin: 0.6em 0 0.4em; line-height: 1.3; font-weight: 700; }
.markdown-body :deep(h2) { font-size: 1.15em; margin: 0.6em 0 0.35em; line-height: 1.3; font-weight: 700; }
.markdown-body :deep(h3) { font-size: 1.05em; margin: 0.5em 0 0.3em; line-height: 1.3; font-weight: 600; }
.markdown-body :deep(h4),.markdown-body :deep(h5),.markdown-body :deep(h6) { font-size: 1em; margin: 0.4em 0 0.3em; font-weight: 600; }
.markdown-body :deep(ul), .markdown-body :deep(ol) { padding-left: 1.5em; margin: 0.4em 0; }
.markdown-body :deep(li) { margin: 0.2em 0; line-height: 1.6; }
.markdown-body :deep(code) { background: rgba(99,102,241,0.15); padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }
.markdown-body :deep(pre) { margin: 0.5em 0; }
.markdown-body :deep(.hljs) { border-radius: 8px; padding: 12px 16px; overflow-x: auto; font-size: 0.85em; background: rgba(15,23,42,0.6); }
.markdown-body :deep(blockquote) { border-left: 3px solid var(--border-medium); padding-left: 1em; color: var(--text-secondary); margin: 0.5em 0; }
.markdown-body :deep(a) { color: #6366f1; }
.markdown-body :deep(table) { border-collapse: collapse; width: 100%; margin: 0.5em 0; }
.markdown-body :deep(th), .markdown-body :deep(td) { border: 1px solid var(--border-subtle); padding: 6px 10px; font-size: 0.9em; }
.markdown-body :deep(hr) { border: none; border-top: 1px solid var(--border-subtle); margin: 0.8em 0; }
</style>
