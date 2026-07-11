// Client for the shared nousergon-auth identity service (vires-ops#60).
// Sign-in (magic link) happens against this cross-origin service; its session
// cookie is set on the parent domain (.nousergon.ai) so it rides along to
// every product host. `credentials: 'include'` is required for that cookie to
// be sent/stored on cross-origin calls.

import { createAuthClient } from 'better-auth/react'
import { magicLinkClient } from 'better-auth/client/plugins'

export const AUTH_URL: string =
  (import.meta.env.VITE_AUTH_URL as string | undefined) ?? 'https://auth.nousergon.ai'

export const authClient = createAuthClient({
  baseURL: AUTH_URL,
  plugins: [magicLinkClient()],
  fetchOptions: { credentials: 'include' },
})
