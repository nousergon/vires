// Short-lived identity JWT for Vires's own API (vires-ops#60).
//
// The shared nousergon-auth session lives in a cross-subdomain cookie the
// FastAPI backend can't verify directly; instead the SPA mints a 15-minute
// JWT from GET /api/auth/token (authenticated by that cookie) and attaches it
// as `Authorization: Bearer` on every /api call. Cached until shortly before
// expiry; refreshed off the still-live session cookie.

import { AUTH_URL } from './authClient'

let cached: { value: string; exp: number } | null = null
let failedAt = 0

// Refresh when less than a minute of validity remains — a token that expires
// mid-request is a pointless 401 round-trip.
const REFRESH_MARGIN_MS = 60_000
// After a failed mint (not signed in to the shared service, or it's
// unreachable), don't re-probe on every single API call — the caller just
// sends the request without a bearer and gets the 401 it deserves.
const RETRY_BACKOFF_MS = 30_000

export async function getIdentityToken(): Promise<string | null> {
  const now = Date.now()
  if (cached && cached.exp * 1000 - now > REFRESH_MARGIN_MS) return cached.value
  if (now - failedAt < RETRY_BACKOFF_MS) return null
  try {
    const res = await fetch(`${AUTH_URL}/api/auth/token`, { credentials: 'include' })
    if (!res.ok) throw new Error(`token mint failed: ${res.status}`)
    const { token } = (await res.json()) as { token: string }
    const exp = (JSON.parse(atob(token.split('.')[1])) as { exp: number }).exp
    cached = { value: token, exp }
    return token
  } catch {
    // Swallowed by design: "no shared session" is an expected state, not an
    // error — the caller sends the request without a bearer and the backend's
    // 401 decides. Recorded via the 30s backoff + the eventual 401 redirect
    // to /login.
    cached = null
    failedAt = now
    return null
  }
}

export function clearIdentityToken(): void {
  cached = null
  failedAt = 0
}
