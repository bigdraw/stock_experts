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
    const p = planDebateRecovery({ isStreaming: true, hasFailedBubble: false, hasSummary: false, hasAgentBubbles: true })
    expect(p.action).toBe('wait')
    expect(p.message).toContain('执行')
  })

  it('maps paused (failed bubble, not streaming) → resume + 重试', () => {
    const p = planDebateRecovery({ isStreaming: false, hasFailedBubble: true, hasSummary: false, hasAgentBubbles: true, lastAgentName: '索罗斯' })
    expect(p.action).toBe('resume')
    expect(p.message).toContain('重试')
    expect(p.message).toContain('索罗斯')
  })

  it('maps completed (summary) → none + 完成', () => {
    const p = planDebateRecovery({ isStreaming: false, hasFailedBubble: false, hasSummary: true, hasAgentBubbles: true })
    expect(p.action).toBe('none')
    expect(p.message).toContain('完成')
  })

  it('maps hard-stopped (agent bubbles, no summary/failure, not streaming) → resume + 被中断 + 轮到X', () => {
    // The user's case: stopped mid-debate (Soros in-flight). The in-flight
    // agent_done wasn't committed, so resume re-runs it; done agents skipped.
    const p = planDebateRecovery({ isStreaming: false, hasFailedBubble: false, hasSummary: false, hasAgentBubbles: true, lastAgentName: '索罗斯' })
    expect(p.action).toBe('resume')
    expect(p.message).toContain('中断')
    expect(p.message).toContain('索罗斯')
  })

  it('hard-stopped message is sensible without lastAgentName', () => {
    const p = planDebateRecovery({ isStreaming: false, hasFailedBubble: false, hasSummary: false, hasAgentBubbles: true })
    expect(p.action).toBe('resume')
    expect(p.message).toContain('中断')
    expect(p.message).not.toContain('轮到')
  })

  it('maps never-started (no agent bubbles, no summary) → none + 尚未开始', () => {
    const p = planDebateRecovery({ isStreaming: false, hasFailedBubble: false, hasSummary: false, hasAgentBubbles: false })
    expect(p.action).toBe('none')
    expect(p.message).toContain('尚未开始')
  })

  it('prioritizes running over failed/hasAgentBubbles (streaming → wait)', () => {
    // a background continuation may still be running while the last live bubble is failed
    const p = planDebateRecovery({ isStreaming: true, hasFailedBubble: true, hasSummary: false, hasAgentBubbles: true })
    expect(p.action).toBe('wait')
  })
})
