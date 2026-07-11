import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderWithProviders } from '../test/utils'
import LoginPage from './LoginPage'
import { authClient } from '../lib/authClient'

vi.mock('../lib/authClient', () => ({
  AUTH_URL: 'https://auth.nousergon.ai',
  authClient: { signIn: { magicLink: vi.fn() } },
}))

const magicLink = vi.mocked(authClient.signIn.magicLink)

beforeEach(() => vi.clearAllMocks())

describe('LoginPage', () => {
  it('requests a magic link from the shared service and shows the check-your-email state', async () => {
    magicLink.mockResolvedValue({ error: null } as never)
    renderWithProviders(<LoginPage />)

    fireEvent.change(screen.getByPlaceholderText('you@example.com'), {
      target: { value: 'brian@example.com' },
    })
    fireEvent.click(screen.getByText('Send login link'))

    await waitFor(() =>
      expect(magicLink).toHaveBeenCalledWith(
        expect.objectContaining({
          email: 'brian@example.com',
          metadata: { product: 'vires' },
        }),
      ),
    )
    expect(await screen.findByText(/Check your email/)).toBeInTheDocument()
    expect(screen.getByText('brian@example.com')).toBeInTheDocument()
  })

  it('surfaces a server error (e.g. rate limit) from the shared service', async () => {
    // The allowlist gate answers uniformly (unapproved looks like success —
    // nousergon-auth#4), so the realistic error a user can still see here is a
    // rate-limit rejection.
    magicLink.mockResolvedValue({
      error: { message: 'Too many requests. Please try again later.' },
    } as never)
    renderWithProviders(<LoginPage />)

    fireEvent.change(screen.getByPlaceholderText('you@example.com'), {
      target: { value: 'friend@example.com' },
    })
    fireEvent.click(screen.getByText('Send login link'))

    expect(await screen.findByText(/Too many requests/)).toBeInTheDocument()
  })

  it('disables the button until an email is entered', () => {
    renderWithProviders(<LoginPage />)
    expect(screen.getByText('Send login link')).toBeDisabled()
  })
})
