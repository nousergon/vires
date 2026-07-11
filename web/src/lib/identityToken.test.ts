import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { getIdentityToken, clearIdentityToken } from './identityToken'

vi.mock('./authClient', () => ({ AUTH_URL: 'https://auth.example.com' }))

function jwtWithExp(exp: number): string {
  return `header.${btoa(JSON.stringify({ exp }))}.sig`
}

function mockTokenFetch(token: string) {
  const f = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ token }) } as Response)
  vi.stubGlobal('fetch', f)
  return f
}

beforeEach(() => {
  clearIdentityToken()
  vi.useFakeTimers()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('getIdentityToken', () => {
  it('mints a token from the auth service and caches it until near expiry', async () => {
    const token = jwtWithExp(Math.floor(Date.now() / 1000) + 900)
    const f = mockTokenFetch(token)

    expect(await getIdentityToken()).toBe(token)
    expect(await getIdentityToken()).toBe(token)
    expect(f).toHaveBeenCalledTimes(1)
    expect(f).toHaveBeenCalledWith('https://auth.example.com/api/auth/token', {
      credentials: 'include',
    })
  })

  it('re-mints once the cached token is within the refresh margin', async () => {
    const shortLived = jwtWithExp(Math.floor(Date.now() / 1000) + 90)
    const f = mockTokenFetch(shortLived)
    await getIdentityToken()

    vi.advanceTimersByTime(45_000) // 45s left < 60s margin
    await getIdentityToken()
    expect(f).toHaveBeenCalledTimes(2)
  })

  it('returns null and backs off when the mint fails', async () => {
    const f = vi.fn().mockResolvedValue({ ok: false, status: 401 } as Response)
    vi.stubGlobal('fetch', f)

    expect(await getIdentityToken()).toBeNull()
    expect(await getIdentityToken()).toBeNull()
    expect(f).toHaveBeenCalledTimes(1) // second call inside the 30s backoff

    vi.advanceTimersByTime(31_000)
    await getIdentityToken()
    expect(f).toHaveBeenCalledTimes(2)
  })

  it('clearIdentityToken drops both the cache and the backoff', async () => {
    const f = vi.fn().mockResolvedValue({ ok: false, status: 401 } as Response)
    vi.stubGlobal('fetch', f)
    await getIdentityToken()

    clearIdentityToken()
    await getIdentityToken()
    expect(f).toHaveBeenCalledTimes(2)
  })
})
