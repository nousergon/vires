import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderWithProviders } from '../test/utils'
import LoginPage from './LoginPage'
import { api } from '../lib/api'

beforeEach(() => vi.restoreAllMocks())

describe('LoginPage', () => {
  it('requests a magic link and shows the check-your-email state', async () => {
    const req = vi.spyOn(api, 'requestMagicLink').mockResolvedValue({ message: 'ok' })
    renderWithProviders(<LoginPage />)

    fireEvent.change(screen.getByPlaceholderText('you@example.com'), {
      target: { value: 'brian@example.com' },
    })
    fireEvent.click(screen.getByText('Send login link'))

    await waitFor(() =>
      expect(req).toHaveBeenCalledWith({ email: 'brian@example.com', invite_code: undefined }),
    )
    expect(await screen.findByText(/Check your email/)).toBeInTheDocument()
    expect(screen.getByText('brian@example.com')).toBeInTheDocument()
  })

  it('passes a trimmed invite code when provided', async () => {
    const req = vi.spyOn(api, 'requestMagicLink').mockResolvedValue({ message: 'ok' })
    renderWithProviders(<LoginPage />)

    fireEvent.change(screen.getByPlaceholderText('you@example.com'), {
      target: { value: 'friend@example.com' },
    })
    fireEvent.change(screen.getByPlaceholderText('only needed the first time'), {
      target: { value: '  abc123  ' },
    })
    fireEvent.click(screen.getByText('Send login link'))

    await waitFor(() =>
      expect(req).toHaveBeenCalledWith({ email: 'friend@example.com', invite_code: 'abc123' }),
    )
  })

  it('shows an error message when the request fails', async () => {
    vi.spyOn(api, 'requestMagicLink').mockRejectedValue(new Error('403: bad invite'))
    renderWithProviders(<LoginPage />)

    fireEvent.change(screen.getByPlaceholderText('you@example.com'), {
      target: { value: 'friend@example.com' },
    })
    fireEvent.click(screen.getByText('Send login link'))

    expect(await screen.findByText('bad invite')).toBeInTheDocument()
  })

  it('disables the button until an email is entered', () => {
    renderWithProviders(<LoginPage />)
    expect(screen.getByText('Send login link')).toBeDisabled()
  })
})
