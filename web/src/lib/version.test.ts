import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchDeployedBuildId, isStale } from './version'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('isStale', () => {
  it('is true only when both ids are real and differ', () => {
    expect(isStale('abc', 'def')).toBe(true)
  })

  it('is false when the ids match', () => {
    expect(isStale('abc', 'abc')).toBe(false)
  })

  it('never fires on a null / unknown / empty deployed id', () => {
    expect(isStale('abc', null)).toBe(false)
    expect(isStale('abc', 'unknown')).toBe(false)
    expect(isStale('abc', '')).toBe(false)
  })

  it("never fires when the running bundle is a local 'dev' / unversioned build", () => {
    expect(isStale('dev', 'abc')).toBe(false)
    expect(isStale('', 'abc')).toBe(false)
    expect(isStale('unknown', 'abc')).toBe(false)
  })
})

function stubFetch(impl: (input: unknown, init?: unknown) => Promise<Response>) {
  const fn = vi.fn(impl)
  vi.stubGlobal('fetch', fn)
  return fn
}

describe('fetchDeployedBuildId', () => {
  it('requests /app/version with no-store and returns the buildId', async () => {
    const fetchMock = stubFetch(async () => new Response(JSON.stringify({ buildId: 'sha123' })))
    const id = await fetchDeployedBuildId()
    expect(id).toBe('sha123')
    expect(fetchMock).toHaveBeenCalledWith('/app/version', expect.objectContaining({ cache: 'no-store' }))
  })

  it('returns null on a non-ok response', async () => {
    stubFetch(async () => new Response('nope', { status: 500 }))
    expect(await fetchDeployedBuildId()).toBeNull()
  })

  it('returns null on a network error', async () => {
    stubFetch(async () => {
      throw new Error('offline')
    })
    expect(await fetchDeployedBuildId()).toBeNull()
  })

  it('returns null when the payload has no usable buildId', async () => {
    stubFetch(async () => new Response(JSON.stringify({ buildId: '' })))
    expect(await fetchDeployedBuildId()).toBeNull()
  })

  it('returns null on non-JSON body', async () => {
    stubFetch(async () => new Response('<html>'))
    expect(await fetchDeployedBuildId()).toBeNull()
  })

  it('forwards an abort signal', async () => {
    const fetchMock = stubFetch(async () => new Response(JSON.stringify({ buildId: 'x' })))
    const ac = new AbortController()
    await fetchDeployedBuildId(ac.signal)
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ signal: ac.signal })
  })
})
