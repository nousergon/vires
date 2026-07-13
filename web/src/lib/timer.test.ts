import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireTimerAlert, fmtClock, unlockAudioForTimers } from './timer'

// A minimal fake AudioContext/Oscillator/Gain graph that just records what was
// asked of it, so a test can assert on pulse count / waveform without a real
// audio backend (unavailable in the vitest/jsdom environment).
class FakeOscillator {
  type = 'sine'
  frequency = { value: 0 }
  connect() {}
  start = vi.fn()
  stop = vi.fn()
}
class FakeGain {
  gain = { setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() }
  connect() {}
}
function stubFakeAudioContext() {
  const oscillators: FakeOscillator[] = []
  class FakeAudioContext {
    state = 'running'
    currentTime = 0
    destination = {}
    createOscillator() {
      const osc = new FakeOscillator()
      oscillators.push(osc)
      return osc
    }
    createGain() {
      return new FakeGain()
    }
    resume() {}
  }
  vi.stubGlobal('AudioContext', FakeAudioContext)
  vi.stubGlobal('navigator', { vibrate: vi.fn() })
  return oscillators
}

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

describe('timer-completion sound vs set-logged ping', () => {
  // `timer.ts` keeps a module-level shared AudioContext singleton, so each
  // test here resets the module registry and re-imports to get a fresh
  // (null) singleton rather than one poisoned by an earlier test's fake.
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.resetModules()
  })

  it('fireTimerAlert plays a pronounced multi-pulse square-wave buzzer', async () => {
    // Reset the module registry BEFORE re-importing — './timer' is already
    // cached from the static import at the top of this file (and its shared
    // AudioContext singleton may already be poisoned by an earlier describe
    // block's fake), so a plain dynamic import would return that same stale
    // instance rather than a fresh one.
    vi.resetModules()
    const oscillators = stubFakeAudioContext()
    const { fireTimerAlert: freshFireTimerAlert } = await import('./timer')

    freshFireTimerAlert({ timer_sound: true, timer_vibration: false, timer_notification: false })

    expect(oscillators.length).toBe(3) // three distinct pulses, not one tone
    expect(oscillators.every((o) => o.type === 'square')).toBe(true)
    expect(oscillators.every((o) => o.start.mock.calls.length === 1)).toBe(true)
  })

  it('firePing (set-logged confirmation) still plays a single short tone', async () => {
    vi.resetModules()
    const oscillators = stubFakeAudioContext()
    const { firePing: freshFirePing } = await import('./timer')

    freshFirePing({ timer_sound: true, timer_vibration: false })

    expect(oscillators.length).toBe(1)
    expect(oscillators[0].type).toBe('sine') // default oscillator type — untouched
  })
})
