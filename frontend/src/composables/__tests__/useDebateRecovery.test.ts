import { describe, it, expect } from 'vitest'
import { isContinueIntent, planDebateRecovery } from '../useDebateRecovery'

describe('isContinueIntent', () => {
  it.each([
    '继续', '请继续', '继续吧', '继续呀', '继续辩论', '恢复', '恢复辩论',
    '重试', '重试辩论', '接着', '往下', 'retry', 'continue', 'resume',
    '继续。。。', '请重试！', '继续。',
  ])('matches pure continue phrase: %s', (t) => {
    expect(isContinueIntent(t)).toBe(true)
  })

  it.each([
    '继续分析茅台的估值', '请继续分析', '帮我继续看看', '你好', ' ', '',
    '123456789012345678901234567', '茅台值不值得买', '分析600519',
  ])('does not match substantive/empty text: %s', (t) => {
    expect(isContinueIntent(t)).toBe(false)
  })
})

describe('planDebateRecovery', () => {
  it('maps running state → wait + "执行" message', () => {
    const p = planDebateRecovery({ isStreaming: true, hasFailedBubble: false, hasSummary: false })
    expect(p.action).toBe('wait')
    expect(p.message).toContain('执行')
  })

  it('maps paused (failed bubble, not streaming) → resume', () => {
    const p = planDebateRecovery({ isStreaming: false, hasFailedBubble: true, hasSummary: false })
    expect(p.action).toBe('resume')
    expect(p.message).toContain('重试')
  })

  it('maps completed (summary, no failure) → none + "完成"', () => {
    const p = planDebateRecovery({ isStreaming: false, hasFailedBubble: false, hasSummary: true })
    expect(p.action).toBe('none')
    expect(p.message).toContain('完成')
  })

  it('maps no-summary-no-failure (interrupted mid-stream, no failed bubble) → none', () => {
    const p = planDebateRecovery({ isStreaming: false, hasFailedBubble: false, hasSummary: false })
    expect(p.action).toBe('none')
  })

  it('prioritizes running over failed (streaming + failed bubble → wait)', () => {
    // a background continuation may still be running while the last live bubble is failed
    const p = planDebateRecovery({ isStreaming: true, hasFailedBubble: true, hasSummary: false })
    expect(p.action).toBe('wait')
  })
})
