import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { authClient } from '../lib/authClient'
import { Button, Card, PageTitle } from '../components/ui'

// Verify-time failures the shared nousergon-auth service's magic-link plugin
// can redirect back with (see its `redirectWithError` call sites) — a dead
// token is by far the common case: the link is single-use and 5-minute-lived,
// so clicking it twice (e.g. from two devices, or an email client's link
// preview/prefetch silently visiting it first) invalidates it before the
// real click lands.
const VERIFY_ERROR_MESSAGES: Record<string, string> = {
  INVALID_TOKEN: 'That link expired or was already used. Enter your email to get a fresh one.',
  failed_to_create_session: "Something went wrong signing you in. Please try again.",
}
const DEFAULT_VERIFY_ERROR_MESSAGE = 'Something went wrong signing you in. Please try again.'

// Passwordless sign-in against the shared nousergon-auth service
// (vires-ops#60). One flow for new and returning users; the service's own
// verify endpoint sets the cross-subdomain session cookie and redirects back
// here — no local /auth/verify page.
//
// New signups are allowlist-gated server-side: an admin pre-approves the
// email address itself (per product) — nothing for the user to type beyond
// their email. Returning users are never gated.
export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [searchParams, setSearchParams] = useSearchParams()
  const verifyError = searchParams.get('error')

  const request = useMutation({
    mutationFn: async () => {
      const { error } = await authClient.signIn.magicLink({
        email,
        callbackURL: `${window.location.origin}/app/`,
        metadata: { product: 'vires' },
      })
      if (error) throw new Error(error.message ?? "Couldn't send the sign-in link.")
    },
    onSuccess: () => {
      // Clear a stale `?error=` once a fresh link is on its way — otherwise
      // it'd resurface after the next failed/successful verify redirect.
      if (verifyError) setSearchParams({}, { replace: true })
      setSent(true)
    },
  })

  if (sent) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-4 text-center">
        <PageTitle>Check your email</PageTitle>
        <p className="text-sm text-slate-400">
          We sent a login link to <span className="text-slate-200">{email}</span>. It works once
          and expires in 5 minutes.
        </p>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col justify-center px-4">
      <PageTitle>Log in to Vires</PageTitle>
      <Card className="space-y-3">
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-400">
            Email
          </label>
          <input
            type="email"
            autoFocus
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            className="w-full rounded-lg bg-slate-800 px-3 py-2.5 text-sm outline-none focus:ring-1 focus:ring-amber-500"
          />
        </div>
        {!request.isError && verifyError && (
          <p className="text-sm text-red-400">
            {VERIFY_ERROR_MESSAGES[verifyError] ?? DEFAULT_VERIFY_ERROR_MESSAGE}
          </p>
        )}
        {request.isError && (
          <p className="text-sm text-red-400">
            {(request.error as Error).message.replace(/^\d+:\s*/, '')}
          </p>
        )}
        <Button
          className="w-full"
          disabled={!email || request.isPending}
          onClick={() => request.mutate()}
        >
          {request.isPending ? 'Sending…' : 'Send login link'}
        </Button>
      </Card>
    </div>
  )
}
