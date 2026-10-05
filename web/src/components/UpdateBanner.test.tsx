import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import UpdateBanner from './UpdateBanner'

// vitest.config injects BUILD_ID = 'test-build'; a different deployed id is stale.
function stubVersion(buildId: string | null, status = 200) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () =>
      buildId === null
        ? new Response('nope', { status: 500 })
        : new Response(JSON.stringify({ buildId }), { status }),
    ),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

const bannerText = /a new version of vires is available/i

describe('UpdateBanner', () => {
  it('surfaces the banner when the deployed build-id differs', async () => {
    stubVersion('a-newer-sha')
    render(<UpdateBanner />)
    expect(await screen.findByText(bannerText)).toBeInTheDocument()
  })

  it('stays hidden when the deployed id matches this bundle', async () => {
    stubVersion('test-build')
    render(<UpdateBanner />)
    // Give the mount check time to resolve, then assert nothing rendered.
    await waitFor(() => expect(fetch).toHaveBeenCalled())
    expect(screen.queryByText(bannerText)).not.toBeInTheDocument()
  })

  it('stays hidden when /version is unreachable', async () => {
    stubVersion(null)
    render(<UpdateBanner />)
    await waitFor(() => expect(fetch).toHaveBeenCalled())
    expect(screen.queryByText(bannerText)).not.toBeInTheDocument()
  })

  it('reloads on tap', async () => {
    stubVersion('a-newer-sha')
    const reload = vi.fn()
    Object.defineProperty(window, 'location', {
      value: { ...window.location, reload },
      configurable: true,
      writable: true,
    })
    render(<UpdateBanner />)
    await userEvent.click(await screen.findByText(bannerText))
    await waitFor(() => expect(reload).toHaveBeenCalled())
  })

  it('waits for a waiting service worker to take control before reloading', async () => {
    stubVersion('a-newer-sha')
    const reload = vi.fn()
    Object.defineProperty(window, 'location', {
      value: { ...window.location, reload },
      configurable: true,
      writable: true,
    })
    const listeners: Array<() => void> = []
    const waiting = { postMessage: vi.fn(() => listeners.forEach((l) => l())) }
    const reg = { update: vi.fn(async () => {}), waiting, installing: null }
    Object.defineProperty(navigator, 'serviceWorker', {
      value: {
        getRegistration: vi.fn(async () => reg),
        addEventListener: (_: string, l: () => void) => listeners.push(l),
        removeEventListener: vi.fn(),
      },
      configurable: true,
    })
    render(<UpdateBanner />)
    await userEvent.click(await screen.findByText(bannerText))
    await waitFor(() => expect(reload).toHaveBeenCalled())
    expect(reg.update).toHaveBeenCalled()
    expect(waiting.postMessage).toHaveBeenCalledWith({ type: 'SKIP_WAITING' })
    Reflect.deleteProperty(navigator, 'serviceWorker')
  })
})
