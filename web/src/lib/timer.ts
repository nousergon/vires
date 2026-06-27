import { useCallback, useEffect, useRef, useState } from 'react'

function beep() {
  try {
    const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
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
    /* vibration not supported */
  }
}

export interface Countdown {
  remaining: number // seconds remaining (0 when idle/done)
  running: boolean
  start: (seconds: number) => void
  stop: () => void
  addSeconds: (delta: number) => void
}

/**
 * Timestamp-based countdown: stores the wall-clock end time and derives
 * `remaining` on each tick, so it stays accurate across tab backgrounding /
 * device sleep (unlike a decrementing counter). Fires beep + haptic at zero.
 */
export function useCountdown(): Countdown {
  const [remaining, setRemaining] = useState(0)
  const [running, setRunning] = useState(false)
  const endRef = useRef<number | null>(null)
  const firedRef = useRef(false)

  useEffect(() => {
    if (!running) return
    const id = setInterval(() => {
      if (endRef.current == null) return
      const left = Math.max(0, Math.round((endRef.current - Date.now()) / 1000))
      setRemaining(left)
      if (left <= 0 && !firedRef.current) {
        firedRef.current = true
        beep()
        vibrate()
        setRunning(false)
      }
    }, 250)
    return () => clearInterval(id)
  }, [running])

  const start = useCallback((seconds: number) => {
    if (seconds <= 0) return
    endRef.current = Date.now() + seconds * 1000
    firedRef.current = false
    setRemaining(seconds)
    setRunning(true)
  }, [])

  const stop = useCallback(() => {
    endRef.current = null
    setRunning(false)
    setRemaining(0)
  }, [])

  const addSeconds = useCallback(
    (delta: number) => {
      if (endRef.current == null) return
      endRef.current += delta * 1000
      setRemaining(Math.max(0, Math.round((endRef.current - Date.now()) / 1000)))
    },
    [],
  )

  return { remaining, running, start, stop, addSeconds }
}

export function fmtClock(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}
