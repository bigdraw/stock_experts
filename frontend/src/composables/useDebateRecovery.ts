/**
 * Natural-language debate recovery (ISSUE: NL resume).
 *
 * When a user types a short continue/retry phrase ("继续" / "恢复" / "重试" /
 * "retry" / ...) on a debate session, the chat input intercepts it and maps the
 * session's state to a reply + action instead of forwarding to the LLM:
 *   - streaming      → "辩论正在执行，请稍等。"      (wait, don't start a 2nd)
 *   - paused (failed) → "上次辩论中断了，正在从失败处重试…" (resume from failure)
 *   - completed       → "该辩论已完成…"              (nothing to resume)
 *
 * These two functions are pure (no Vue / store deps) so they're unit-testable.
 */

export interface DebateRecoveryInput {
  /** Is a debate stream currently running for this session? */
  isStreaming: boolean
  /** Does the last assistant bubble (before the user's "继续") carry an error
   *  flag (agent_failed / summary_failed → paused)? */
  hasFailedBubble: boolean
  /** Does a summary bubble exist (debate reached completion)? */
  hasSummary: boolean
}

export type RecoveryAction = 'wait' | 'resume' | 'none'

export interface DebateRecoveryPlan {
  message: string
  action: RecoveryAction
}

// Match a short continue/retry phrase. Optional 请/你/我 prefix, a continue
// keyword, an optional 吧/呀/呢/了/辩论 suffix, trailing punctuation. Anchored
// so "继续分析茅台" / "请继续分析" don't hijack a substantive message.
const CONTINUE_RE =
  /^(?:请|你|我)?(?:继续|恢复|重试|接着|往下|retry|continue|resume)(?:辩论|吧|呀|呢|了)?[。.!！？?…~]*$/i

export function isContinueIntent(text: string): boolean {
  const t = (text || '').trim()
  if (!t || t.length > 24) return false
  return CONTINUE_RE.test(t)
}

export function planDebateRecovery(state: DebateRecoveryInput): DebateRecoveryPlan {
  if (state.isStreaming) {
    return { message: '辩论正在执行，请稍等。', action: 'wait' }
  }
  if (state.hasFailedBubble) {
    return { message: '上次辩论中断了，正在从失败处重试…', action: 'resume' }
  }
  if (state.hasSummary) {
    return {
      message: '该辩论已完成，没有待恢复的内容。可点 ⚖️ 开始辩论 开启新辩论。',
      action: 'none',
    }
  }
  return { message: '该辩论没有可恢复的中断点。', action: 'none' }
}
