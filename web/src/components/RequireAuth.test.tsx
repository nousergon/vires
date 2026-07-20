import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, render, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import RequireAuth from './RequireAuth'
import { api } from '../lib/api'

beforeEach(() => vi.restoreAllMocks())

function LoginPageStub() {
  const location = useLocation()
  return <div>Login page{location.search}</div>
}

function renderGuarded(initialEntry = '/train') {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route
            path="/train"
            element={
              <RequireAuth>
                <div>Protected train page</div>
              </RequireAuth>
            }
          />
          <Route path="/login" element={<LoginPageStub />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('RequireAuth', () => {
  it('renders the guarded children once /auth/me resolves authenticated', async () => {
    vi.spyOn(api, 'getMe').mockResolvedValue({
      email: 'brian@example.com',
      display_name: null,
      is_admin: true,
    })
    renderGuarded()
    expect(await screen.findByText('Protected train page')).toBeInTheDocument()
  })

  it('redirects to /login when /auth/me 401s', async () => {
    vi.spyOn(api, 'getMe').mockRejectedValue(new Error('401: Not authenticated'))
    renderGuarded()
    await waitFor(() => expect(screen.getByText('Login page')).toBeInTheDocument())
    expect(screen.queryByText('Protected train page')).not.toBeInTheDocument()
  })

  it('preserves a failed magic-link verify `?error=` param through the /login redirect', async () => {
    vi.spyOn(api, 'getMe').mockRejectedValue(new Error('401: Not authenticated'))
    renderGuarded('/train?error=INVALID_TOKEN')
    await waitFor(() =>
      expect(screen.getByText('Login page?error=INVALID_TOKEN')).toBeInTheDocument(),
    )
  })
})
