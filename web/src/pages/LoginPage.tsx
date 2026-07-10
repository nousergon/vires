import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api } from '../lib/api'
import { Button, Card, PageTitle } from '../components/ui'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const [sent, setSent] = useState(false)

  const request = useMutation({
    mutationFn: () =>
      api.requestMagicLink({
        email,
        invite_code: inviteCode.trim() || undefined,
      }),
    onSuccess: () => setSent(true),
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
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-400">
            Invite code <span className="normal-case text-slate-500">(new accounts only)</span>
          </label>
          <input
            type="text"
            value={inviteCode}
            onChange={(e) => setInviteCode(e.target.value)}
            placeholder="only needed the first time"
            className="w-full rounded-lg bg-slate-800 px-3 py-2.5 text-sm outline-none focus:ring-1 focus:ring-amber-500"
          />
        </div>
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
