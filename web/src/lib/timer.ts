import { useCallback, useEffect, useRef, useState } from 'react'

function beep() {
  try {
    const Ctx =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    const ctx = new Ctx()
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
    osc.onended = () => ctx.close()
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
  if (prefs.timer_sound) beep()
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
          beep()
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

  return { remaining, total, running, start, stop, addSeconds, setDuration }
}

export function fmtClock(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}
