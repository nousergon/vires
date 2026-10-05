import { useCallback, useEffect, useRef, useState } from 'react'
import { BUILD_ID, fetchDeployedBuildId, isStale } from '../lib/version'

// How often to re-check while the tab is visible. One tiny no-store GET; 5 min
// balances promptness against noise. We also check on every foreground/focus,
// which is the common case for an installed PWA reopened after a deploy.
const POLL_MS = 5 * 60 * 1000
// Upper bound on waiting for a new service worker to take control on tap.
const ACTIVATE_WAIT_MS = 4000

// Fetch the new SW, ask a waiting one to activate, and resolve when it takes
// control of this page (or after ACTIVATE_WAIT_MS, whichever comes first).
async function activateNewWorker(): Promise<void> {
  const sw = navigator.serviceWorker
  const reg = await sw?.getRegistration()
  if (!sw || !reg) return
  await reg.update()
  const pending = reg.waiting ?? reg.installing
  if (!pending) return
  await new Promise<void>((resolve) => {
    const done = () => {
      sw.removeEventListener('controllerchange', done)
      window.clearTimeout(timer)
      resolve()
    }
    const timer = window.setTimeout(done, ACTIVATE_WAIT_MS)
    sw.addEventListener('controllerchange', done)
    // Workbox's generated SW honours SKIP_WAITING; autoUpdate builds also
    // skipWaiting on their own, in which case this is a no-op.
    reg.waiting?.postMessage({ type: 'SKIP_WAITING' })
  })
}

// Proactive "update available" banner (vires-ops#59). Polls /version on mount,
// on every foreground/focus, and on an interval while visible; the moment the
// deployed build-id diverges from this bundle's it shows a persistent,
// one-tap-to-reload banner. The DETECTION is independent of the service worker
// (see lib/version.ts) — only the reload nudges the SW, best-effort.
export default function UpdateBanner() {
  const [stale, setStale] = useState(false)
  const staleRef = useRef(false)
  const abortRef = useRef<AbortController | null>(null)

  const check = useCallback(async () => {
    if (staleRef.current) return // already surfaced — stop polling
    const ac = new AbortController()
    abortRef.current?.abort()
    abortRef.current = ac
    const deployed = await fetchDeployedBuildId(ac.signal)
    if (isStale(BUILD_ID, deployed)) {
      staleRef.current = true
      setStale(true)
    }
  }, [])

  useEffect(() => {
    void check()
    const onForeground = () => {
      if (document.visibilityState === 'visible') void check()
    }
    document.addEventListener('visibilitychange', onForeground)
    window.addEventListener('focus', onForeground)
    const timer = window.setInterval(onForeground, POLL_MS)
    return () => {
      document.removeEventListener('visibilitychange', onForeground)
      window.removeEventListener('focus', onForeground)
      window.clearInterval(timer)
      abortRef.current?.abort()
    }
  }, [check])

  const reload = useCallback(() => {
    // Best-effort: get the new SW in control BEFORE reloading. reg.update()
    // resolves once the new worker is fetched, not once it is active, so an
    // immediate reload is still served the old precached bundle — and the
    // banner comes straight back. Wait (bounded) for the controller to change.
    // The detection above never depended on this succeeding; reload regardless.
    void (async () => {
      try {
        await activateNewWorker()
      } catch {
        // ignore — the reload still happens
      }
      window.location.reload()
    })()
  }, [])

  if (!stale) return null

  return (
    <div className="fixed inset-x-0 top-0 z-50 mx-auto max-w-2xl px-2 pt-2 safe-top">
      <button
        type="button"
        onClick={reload}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-slate-900 shadow-lg"
      >
        <span aria-hidden>↻</span>
        A new version of Vires is available — tap to reload
      </button>
    </div>
  )
}
