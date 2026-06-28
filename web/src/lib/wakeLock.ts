import { useEffect } from 'react'

interface WakeLockSentinelLike {
  released: boolean
  release: () => Promise<void>
}
interface WakeLockNavigator {
  wakeLock?: { request: (type: 'screen') => Promise<WakeLockSentinelLike> }
}

/**
 * Hold a screen wake-lock while `active` — keeps the phone from sleeping during a
 * running timer so the end-of-timer sound/visual reliably fire (the browser
 * suspends background JS + audio when the screen sleeps). The OS auto-releases the
 * lock when the tab is hidden, so we re-acquire on visibility change.
 */
export function useWakeLock(active: boolean) {
  useEffect(() => {
    const nav = navigator as Navigator & WakeLockNavigator
    if (!active || !nav.wakeLock) return

    let sentinel: WakeLockSentinelLike | null = null
    let cancelled = false

    async function acquire() {
      try {
        const s = await nav.wakeLock!.request('screen')
        if (cancelled) {
          void s.release()
        } else {
          sentinel = s
        }
      } catch {
        /* denied or unsupported — no-op */
      }
    }

    function onVisibility() {
      if (document.visibilityState === 'visible' && (!sentinel || sentinel.released)) {
        void acquire()
      }
    }

    void acquire()
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      cancelled = true
      document.removeEventListener('visibilitychange', onVisibility)
      if (sentinel && !sentinel.released) void sentinel.release()
    }
  }, [active])
}
