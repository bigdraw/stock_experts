/**
 * Resize sync composable — watches an element's height and syncs it to a CSS
 * variable, with an optional callback for side effects (e.g. sync scroll).
 *
 * Solves the "input area grows → message padding must follow" layout-stability
 * problem without hardcoding ResizeObserver + CSS-var logic in every view.
 *
 * Usage:
 *   useResizeSync(inputAreaRef, '--input-area-h', (h) => {
 *     if (autoScroll.value && msgList.value) msgList.value.scrollTop = msgList.value.scrollHeight
 *   })
 */

import { onMounted, onUnmounted, type Ref } from 'vue'

export function useResizeSync(
  target: Ref<HTMLElement | null>,
  cssVar: string,
  onResize?: (height: number) => void,
) {
  let _observer: ResizeObserver | null = null

  onMounted(() => {
    if (!target.value) return
    const update = () => {
      const h = target.value?.offsetHeight ?? 0
      document.documentElement.style.setProperty(cssVar, `${h}px`)
      onResize?.(h)
    }
    update()
    _observer = new ResizeObserver(update)
    _observer.observe(target.value)
  })

  onUnmounted(() => {
    _observer?.disconnect()
    _observer = null
  })
}
