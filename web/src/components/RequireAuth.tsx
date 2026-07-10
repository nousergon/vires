import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../lib/useAuth'
import { Spinner } from './ui'

// Gates every tabbed-app route on a valid session. `/login` and
// `/auth/verify` are public and never pass through here (see App.tsx).
// Its own file (not inlined in App.tsx) so it's testable without pulling in
// vite-plugin-pwa's virtual module, which vitest's config deliberately
// excludes (see vitest.config.ts) — App.tsx itself is untestable directly.
export default function RequireAuth({ children }: { children: ReactNode }) {
  const { me, isLoading } = useAuth()
  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner />
      </div>
    )
  }
  if (!me) return <Navigate to="/login" replace />
  return <>{children}</>
}
