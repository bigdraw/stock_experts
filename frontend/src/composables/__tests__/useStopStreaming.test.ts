import { describe, it, expect } from 'vitest'
import { shouldPostStop } from '../useStopStreaming'

describe('shouldPostStop', () => {
  it('returns true for a debate session (POST /stop before abort)', () => {
    expect(shouldPostStop('debate')).toBe(true)
  })

  it('returns false for a chat session (bare abort is enough)', () => {
    expect(shouldPostStop('chat')).toBe(false)
  })

  it('returns false for undefined session type', () => {
    expect(shouldPostStop(undefined)).toBe(false)
  })
})
