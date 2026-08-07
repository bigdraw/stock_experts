/**
 * Scroll anchoring composable — manages auto-scroll-to-bottom for streaming
 * content (chat tokens, debate events). Handles:
 * - autoScroll flag (user scrolled up → stop following; back near bottom → resume)
 * - rAF-throttled scroll (batch multiple content deltas into one scroll per frame)
 * - force scroll-to-bottom (user actions: send / retry / new session)
 *
 * Usage:
 *   const { autoScroll, onScroll, maybeScrollToBottom, scrollToBottom } = useScrollAnchoring(msgList)
 *   <div ref="msgList" @scroll="onScroll">
 *   watch(() => messages.at(-1)?.content, () => maybeScrollToBottom())
 */

import { ref, nextTick, type Ref } from 'vue'

const BOTTOM_THRESHOLD = 80 // px from bottom to consider "anchored"

export function useScrollAnchoring(scrollEl: Ref<HTMLElement | null>) {
  const autoScroll = ref(true)
  let _rafPending = false

  /** Bind to @scroll on the scroll container. Tracks whether user is near bottom. */
  function onScroll() {
    const el = scrollEl.value
    if (!el) return
    autoScroll.value = el.scrollHeight - el.scrollTop - el.clientHeight < BOTTOM_THRESHOLD
  }

  /**
   * Request a scroll-to-bottom on the next animation frame. Multiple calls
   * within the same frame are coalesced — prevents per-token scrollTop jumps.
   * No-op if user has scrolled away from the bottom.
   */
  function maybeScrollToBottom() {
    if (!autoScroll.value) return
    if (_rafPending) return
    _rafPending = true
    requestAnimationFrame(() => {
      _rafPending = false
      const el = scrollEl.value
      if (el) el.scrollTop = el.scrollHeight
    })
  }

  /**
   * Force scroll-to-bottom immediately (user action: send / retry / new session).
   * Resets autoScroll to true.
   */
  async function scrollToBottom() {
    autoScroll.value = true
    await nextTick()
    const el = scrollEl.value
    if (el) el.scrollTop = el.scrollHeight
  }

  return { autoScroll, onScroll, maybeScrollToBottom, scrollToBottom }
}
