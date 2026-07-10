import { useEffect, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { Button, PageTitle, Spinner } from '../components/ui'

export default function VerifyPage() {
  const [params] = useSearchParams()
  const token = params.get('token')
  const nav = useNavigate()
  const qc = useQueryClient()
  // The token is single-use — a ref guard (not just `enabled`) makes sure it
  // fires exactly once even under React 18 StrictMode's dev-only double
  // mount/unmount/remount, which would otherwise burn the token on the
  // second attempt and show a false "expired" error.
  const firedRef = useRef(false)

  const verify = useMutation({
    mutationFn: () => api.verifyMagicLink(token as string),
    onSuccess: () => {
      qc.invalidateQueries()
      nav('/train', { replace: true })
    },
  })

  useEffect(() => {
    if (firedRef.current || !token) return
    firedRef.current = true
    verify.mutate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  if (!token) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-4 text-center">
        <PageTitle>Missing login link</PageTitle>
        <Button onClick={() => nav('/login')}>Back to login</Button>
      </div>
    )
  }

  if (verify.isError) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-4 text-center">
        <PageTitle>That link didn't work</PageTitle>
        <p className="text-sm text-slate-400">
          It may have expired or already been used. Request a new one.
        </p>
        <Button onClick={() => nav('/login')}>Back to login</Button>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col items-center justify-center">
      <Spinner />
      <p className="mt-2 text-sm text-slate-400">Logging you in…</p>
    </div>
  )
}
