import { useCallback, useEffect, useRef, useState } from 'react'

// A single shared, reused AudioContext. iOS Safari (and other mobile
// browsers under autoplay/power policies) silently suspends a *freshly
// created* AudioContext unless it's created/resumed synchronously inside a
// user gesture — the timer-completion beep fires later from a setInterval
// callback, well outside any gesture, so a fresh-context-per-beep (the prior
// approach) plays no audible sound at all on those browsers, with no error.
// `unlockAudioForTimers` resumes this shared context from an actual tap
// (starting a rest/hold timer) so the later, gesture-less beep reuses an
// already-running context instead of creating a doomed-to-be-suspended one.
let sharedAudioCtx: AudioContext | null = null

function getAudioContext(): AudioContext | null {
  try {
    const Ctx =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    if (!sharedAudioCtx) sharedAudioCtx = new Ctx()
    return sharedAudioCtx
  } catch {
    return null
  }
}

/** Call from a real user-gesture handler that starts a timer (e.g. "mark set
 * done" / "start hold") so the alert that fires later, unattended, can
 * actually be heard. Safe to call repeatedly. */
export function unlockAudioForTimers() {
  const ctx = getAudioContext()
  if (ctx?.state === 'suspended') void ctx.resume()
}

function beep() {
  try {
    const ctx = getAudioContext()
    if (!ctx) return
    if (ctx.state === 'suspended') void ctx.resume()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.frequency.value = 880
    gain.gain.setValueAtTime(0.001, ctx.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.3, ctx.currentTime + 0.02)
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4)
    osc.start()
    osc.stop(ctx.currentTime + 0.42)
  } catch {
    /* audio not available */
  }
}

// Timer-completion alert: a harsher, more attention-grabbing sound than the
// single-tone `beep()` used for in-app confirmations — three short square-wave
// pulses (buzzer timbre, lower pitch, louder) so it reads as a distinct "rest
// is over" signal rather than a soft chime, and is more likely to be noticed
// from across a gym floor or with the phone in a pocket.
function buzz() {
  try {
    const ctx = getAudioContext()
    if (!ctx) return
    if (ctx.state === 'suspended') void ctx.resume()
    const pulseCount = 3
    const pulseDuration = 0.14
    const gapDuration = 0.09
    for (let i = 0; i < pulseCount; i++) {
      const t0 = ctx.currentTime + i * (pulseDuration + gapDuration)
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.connect(gain)
      gain.connect(ctx.destination)
      osc.type = 'square'
      osc.frequency.value = 440
      gain.gain.setValueAtTime(0.001, t0)
      gain.gain.exponentialRampToValueAtTime(0.5, t0 + 0.015)
      gain.gain.exponentialRampToValueAtTime(0.001, t0 + pulseDuration)
      osc.start(t0)
      osc.stop(t0 + pulseDuration + 0.02)
    }
  } catch {
    /* audio not available */
  }
}

function vibrate() {
  try {
    navigator.vibrate?.([120, 60, 120])
  } catch {
    /* vibration not supported (e.g. iOS Safari) */
  }
}

function showNotification(title: string) {
  try {
    if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return
    // Prefer the service worker registration (works on installed PWAs); fall back
    // to a page Notification when no SW controls the page.
    void navigator.serviceWorker?.ready
      .then((reg) => reg.showNotification(title, { tag: 'vires-timer' }))
      .catch(() => {
        new Notification(title)
      })
  } catch {
    /* notifications not available */
  }
}

export interface TimerAlertPrefs {
  timer_sound: boolean
  timer_vibration: boolean
  timer_notification: boolean
}

/** Fire the configured end-of-timer alerts. `label` titles the notification. */
export function fireTimerAlert(prefs: TimerAlertPrefs, label = 'Timer done') {
  if (prefs.timer_sound) buzz()
  if (prefs.timer_vibration) vibrate()
  if (prefs.timer_notification) showNotification(label)
}

/** A short sound + vibration confirmation — used when a set is logged (no
 * notification: the user is in-app tapping ✓, unlike a backgrounded timer). */
export function firePing(prefs: Pick<TimerAlertPrefs, 'timer_sound' | 'timer_vibration'>) {
  if (prefs.timer_sound) beep()
  if (prefs.timer_vibration) vibrate()
}

/** Ask for notification permission (call when the user enables the toggle). */
export async function requestNotificationPermission(): Promise<boolean> {
  if (typeof Notification === 'undefined') return false
  if (Notification.permission === 'granted') return true
  if (Notification.permission === 'denied') return false
  return (await Notification.requestPermission()) === 'granted'
}

export interface Countdown {
  remaining: number // seconds remaining (0 when idle/done)
  total: number // seconds the current countdown was started with (for a progress bar)
  running: boolean
  start: (seconds: number, onFinish?: () => void, label?: string) => void
  stop: () => void
  finish: () => void
  addSeconds: (delta: number) => void
  setDuration: (seconds: number) => void
}

/**
 * Timestamp-based countdown: stores the wall-clock end time and derives
 * `remaining` on each tick, so it stays accurate across tab backgrounding /
 * device sleep (unlike a decrementing counter). At zero it calls `onAlert(label)`
 * (the caller fires the configured sound/vibration/notification) then `onFinish`.
 */
export function useCountdown(onAlert?: (label?: string) => void): Countdown {
  const [remaining, setRemaining] = useState(0)
  const [total, setTotal] = useState(0)
  const [running, setRunning] = useState(false)
  const endRef = useRef<number | null>(null)
  const firedRef = useRef(false)
  const labelRef = useRef<string | undefined>(undefined)
  const onFinishRef = useRef<(() => void) | null>(null)
  const onAlertRef = useRef(onAlert)
  useEffect(() => {
    onAlertRef.current = onAlert
  }, [onAlert])

  useEffect(() => {
    if (!running) return
    const id = setInterval(() => {
      if (endRef.current == null) return
      const left = Math.max(0, Math.round((endRef.current - Date.now()) / 1000))
      setRemaining(left)
      if (left <= 0 && !firedRef.current) {
        firedRef.current = true
        if (onAlertRef.current) onAlertRef.current(labelRef.current)
        else {
          buzz()
          vibrate()
        }
        setRunning(false)
        const cb = onFinishRef.current
        onFinishRef.current = null
        cb?.()
      }
    }, 250)
    return () => clearInterval(id)
  }, [running])

  const start = useCallback((seconds: number, onFinish?: () => void, label?: string) => {
    if (seconds <= 0) return
    endRef.current = Date.now() + seconds * 1000
    firedRef.current = false
    labelRef.current = label
    onFinishRef.current = onFinish ?? null
    setTotal(seconds)
    setRemaining(seconds)
    setRunning(true)
  }, [])

  const stop = useCallback(() => {
    endRef.current = null
    onFinishRef.current = null
    setRunning(false)
    setRemaining(0)
  }, [])

  // Complete the countdown NOW, as if it had reached zero — runs the onFinish
  // callback (e.g. a hold logging its set and rolling into the rest timer) but
  // WITHOUT firing the end alert, since this is a deliberate user tap rather
  // than an unattended timeout. Backs the hold bar's "Done" button so finishing
  // a plank early still logs the set and starts rest instead of silently
  // aborting (which the old "Stop" did).
  const finish = useCallback(() => {
    if (endRef.current == null) return
    firedRef.current = true
    endRef.current = null
    setRunning(false)
    setRemaining(0)
    const cb = onFinishRef.current
    onFinishRef.current = null
    cb?.()
  }, [])

  const addSeconds = useCallback((delta: number) => {
    if (endRef.current == null) return
    endRef.current += delta * 1000
    setRemaining(Math.max(0, Math.round((endRef.current - Date.now()) / 1000)))
  }, [])

  // Re-base a running countdown to an exact number of seconds ("change the
  // number of seconds on the fly"). Resets the fired latch so a re-extended
  // timer alerts again at the new zero.
  const setDuration = useCallback((seconds: number) => {
    if (endRef.current == null || seconds <= 0) return
    endRef.current = Date.now() + seconds * 1000
    firedRef.current = false
    setTotal(seconds)
    setRemaining(seconds)
  }, [])

  return { remaining, total, running, start, stop, finish, addSeconds, setDuration }
}

export function fmtClock(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}
