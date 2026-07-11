// SW-independent staleness detection (vires-ops#59).
//
// The service worker's own `autoUpdate` path can silently break — a bug, a
// platform quirk, or just a very-long-lived tab — and leave an installed PWA
// running days-old JS with no signal to the user. That is exactly what happened
// on 2026-07-10: an installed app started a workout against pre-2026-07-05 code,
// silently skipping the ailment check-in gate, and had been stale for at least
// five days with no indication.
//
// This module is a deliberately SW-independent net: the id this bundle was
// compiled with (`__BUILD_ID__`, injected by Vite) compared against a plain
// `fetch('/version')` of what the backend currently serves. It relies on
// nothing about the SW registering, activating, or calling
// skipWaiting/clientsClaim — so it still fires if the SW update path breaks
// again. Pure functions live here; the polling hook + banner live in
// components/UpdateBanner.tsx.

// The build-id this bundle was compiled with (git short SHA in CI, 'dev'
// locally when no VITE_BUILD_ID / git is available).
export const BUILD_ID: string = __BUILD_ID__

// Sentinels that mean "can't tell" and must never trigger the banner. 'dev' is
// what an un-versioned local bundle reports; 'unknown' is what the backend
// returns when no build is on disk (see api/routers/version.py).
const NO_SIGNAL = new Set(['', 'dev', 'unknown'])

// Fetch the deployed build-id from the backend. Never throws — any network or
// parse error resolves to null so a transient blip never shows a false banner.
export async function fetchDeployedBuildId(signal?: AbortSignal): Promise<string | null> {
  try {
    const resp = await fetch('/version', { cache: 'no-store', signal })
    if (!resp.ok) return null
    const body: unknown = await resp.json()
    const id = (body as { buildId?: unknown } | null)?.buildId
    return typeof id === 'string' && id.length > 0 ? id : null
  } catch {
    return null
  }
}

// True iff we can confidently say the running bundle is stale: we know our own
// real id, the server reports a real id, and they differ. Any sentinel on
// either side (local dev, no-build backend, network blip) yields false.
export function isStale(current: string, deployed: string | null): boolean {
  if (deployed == null || NO_SIGNAL.has(deployed)) return false
  if (NO_SIGNAL.has(current)) return false
  return current !== deployed
}
