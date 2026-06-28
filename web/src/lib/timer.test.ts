import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireTimerAlert, fmtClock } from './timer'

describe('fmtClock', () => {
  it('formats m:ss with zero-padded seconds', () => {
    expect(fmtClock(0)).toBe('0:00')
    expect(fmtClock(5)).toBe('0:05')
    expect(fmtClock(65)).toBe('1:05')
    expect(fmtClock(600)).toBe('10:00')
    expect(fmtClock(3599)).toBe('59:59')
  })
})

describe('fireTimerAlert', () => {
  afterEach(() => vi.restoreAllMocks())

  it('vibrates only when timer_vibration is on', () => {
    const vibe = vi.fn()
    vi.stubGlobal('navigator', { ...navigator, vibrate: vibe })

    fireTimerAlert({ timer_sound: false, timer_vibration: true, timer_notification: false })
    expect(vibe).toHaveBeenCalledTimes(1)

    vibe.mockClear()
    fireTimerAlert({ timer_sound: false, timer_vibration: false, timer_notification: false })
    expect(vibe).not.toHaveBeenCalled()

    vi.unstubAllGlobals()
  })
})
