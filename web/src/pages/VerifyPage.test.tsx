import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor, render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import VerifyPage from './VerifyPage'
import { api } from '../lib/api'
import { renderWithProviders } from '../test/utils'

beforeEach(() => vi.restoreAllMocks())

// A miniature version of App's real route table so a successful verify's
// navigation to /train is actually observable (not just the API call).
function renderAtVerifyRoute(path: string) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/auth/verify" element={<VerifyPage />} />
          <Route path="/train" element={<div>Train page</div>} />
          <Route path="/login" element={<div>Login page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('VerifyPage', () => {
  it('verifies the token and navigates to /train on success', async () => {
    const verify = vi.spyOn(api, 'verifyMagicLink').mockResolvedValue({
      email: 'brian@example.com',
      display_name: null,
      is_admin: true,
    })
    renderAtVerifyRoute('/auth/verify?token=abc123')

    await waitFor(() => expect(verify).toHaveBeenCalledWith('abc123'))
    expect(await screen.findByText('Train page')).toBeInTheDocument()
  })

  it('verifies the token exactly once (StrictMode-safe)', async () => {
    const verify = vi.spyOn(api, 'verifyMagicLink').mockResolvedValue({
      email: 'brian@example.com',
      display_name: null,
      is_admin: false,
    })
    renderAtVerifyRoute('/auth/verify?token=abc123')
    await waitFor(() => expect(verify).toHaveBeenCalledTimes(1))
  })

  it('shows an error and a way back to login on an invalid/expired token', async () => {
    vi.spyOn(api, 'verifyMagicLink').mockRejectedValue(new Error('401: expired'))
    renderWithProviders(<VerifyPage />, { route: '/auth/verify?token=stale' })

    expect(await screen.findByText(/didn't work/)).toBeInTheDocument()
    expect(screen.getByText('Back to login')).toBeInTheDocument()
  })

  it('shows a missing-link state with no token in the URL', () => {
    renderWithProviders(<VerifyPage />, { route: '/auth/verify' })
    expect(screen.getByText('Missing login link')).toBeInTheDocument()
  })
})
