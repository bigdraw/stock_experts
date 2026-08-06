/**
 * Pure helper for the stop button's debate-vs-chat branching (ISSUE: hard-stop).
 *
 * The 停止 button calls stopStreaming(); for a debate session it must POST
 * /debate/sessions/{id}/stop (to set the backend hard-stop flag) BEFORE
 * aborting the SSE fetch — otherwise the backend's CancelledError handler
 * spawns a background continuation (ISSUE-015) and the debate keeps running.
 * Chat (non-debate) sessions have no background continuation, so a bare abort
 * fully stops them. This function decides whether to POST.
 */
export function shouldPostStop(
  sessionType: 'chat' | 'debate' | undefined,
): boolean {
  return sessionType === 'debate'
}
