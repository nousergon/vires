import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireTimerAlert, fmtClock, unlockAudioForTimers } from './timer'

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
    // Stub without spreading the global navigator — it's undefined in CI's Node env.
    vi.stubGlobal('navigator', { vibrate: vibe })

    fireTimerAlert({ timer_sound: false, timer_vibration: true, timer_notification: false })
    expect(vibe).toHaveBeenCalledTimes(1)

    vibe.mockClear()
    fireTimerAlert({ timer_sound: false, timer_vibration: false, timer_notification: false })
    expect(vibe).not.toHaveBeenCalled()

    vi.unstubAllGlobals()
  })
})

describe('unlockAudioForTimers', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('resumes a suspended shared AudioContext once, not again once running', () => {
    // Models iOS Safari's real autoplay policy: a fresh context starts
    // suspended; resume() (mocked here to flip state, like the real API
    // does asynchronously) brings it to 'running'. The shared context is a
    // module-level singleton, so both calls here exercise the SAME instance.
    const resume = vi.fn(function (this: { state: string }) {
      this.state = 'running'
    })
    class FakeAudioContext {
      state = 'suspended'
      resume = resume
    }
    vi.stubGlobal('AudioContext', FakeAudioContext)

    unlockAudioForTimers()
    expect(resume).toHaveBeenCalledTimes(1)

    unlockAudioForTimers()
    expect(resume).toHaveBeenCalledTimes(1) // already running — not resumed again
  })
})
