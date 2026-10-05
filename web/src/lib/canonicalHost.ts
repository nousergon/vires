// The Vires app is served to browsers at vires.nousergon.ai/app (a Cloudflare
// Worker forwards /app* to the EC2 origin). That origin's own hostname,
// vires-app.nousergon.ai, is publicly resolvable and serves the very same
// build — but sign-in there can never work: the shared nousergon-auth service
// only grants CORS to the trusted product origins, so the magic-link POST from
// vires-app.nousergon.ai is blocked by the browser and surfaces as the bare
// "Failed to fetch". Anyone who lands on (or installed the PWA from) the origin
// hostname is sent to the canonical one before the app boots.

export const ORIGIN_HOST = 'vires-app.nousergon.ai'
export const CANONICAL_ORIGIN = 'https://vires.nousergon.ai'

// Returns the URL to move to, or null when already on a usable host.
export function canonicalRedirect(loc: Pick<Location, 'hostname' | 'pathname' | 'search' | 'hash'>): string | null {
  if (loc.hostname !== ORIGIN_HOST) return null
  return `${CANONICAL_ORIGIN}${loc.pathname}${loc.search}${loc.hash}`
}
