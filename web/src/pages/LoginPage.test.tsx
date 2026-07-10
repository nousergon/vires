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

    await waitFor(() => expect(req).toHaveBeenCalledWith('brian@example.com'))
    expect(await screen.findByText(/Check your email/)).toBeInTheDocument()
    expect(screen.getByText('brian@example.com')).toBeInTheDocument()
  })

  it('shows an error message when the email is not allowlisted', async () => {
    vi.spyOn(api, 'requestMagicLink').mockRejectedValue(
      new Error("403: That email hasn't been invited yet."),
    )
    renderWithProviders(<LoginPage />)

    fireEvent.change(screen.getByPlaceholderText('you@example.com'), {
      target: { value: 'friend@example.com' },
    })
    fireEvent.click(screen.getByText('Send login link'))

    expect(await screen.findByText(/hasn't been invited yet/)).toBeInTheDocument()
  })

  it('disables the button until an email is entered', () => {
    renderWithProviders(<LoginPage />)
    expect(screen.getByText('Send login link')).toBeDisabled()
  })
})
