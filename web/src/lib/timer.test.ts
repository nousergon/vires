import { describe, expect, it } from 'vitest'
import { fmtClock } from './timer'

describe('fmtClock', () => {
  it('formats m:ss with zero-padded seconds', () => {
    expect(fmtClock(0)).toBe('0:00')
    expect(fmtClock(5)).toBe('0:05')
    expect(fmtClock(65)).toBe('1:05')
    expect(fmtClock(600)).toBe('10:00')
    expect(fmtClock(3599)).toBe('59:59')
  })
})
