import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { logSetOfflineFirst, drainQueue } from './setSync'
import { listPending, count, type PendingSet, type QueueBackend } from './setQueue'
import { api } from './api'

function memBackend(): QueueBackend {
  const map = new Map<string, PendingSet>()
  return {
    getAll: async () => [...map.values()],
    put: async (e) => {
      map.set(e.clientUuid, e)
    },
    delete: async (k) => {
      map.delete(k)
    },
    clear: async () => {
      map.clear()
    },
  }
}

function setOnline(v: boolean) {
  Object.defineProperty(navigator, 'onLine', { value: v, configurable: true })
}

let backend: QueueBackend
beforeEach(() => {
  backend = memBackend()
  setOnline(true)
  // Background Sync + SW absent in jsdom → registerSync() short-circuits false.
})
afterEach(() => vi.restoreAllMocks())

describe('logSetOfflineFirst', () => {
  it('POSTs immediately when online and does not enqueue', async () => {
    const logSet = vi
      .spyOn(api, 'logSet')
      .mockResolvedValue({ id: 7, set_number: 1 } as never)
    const r = await logSetOfflineFirst(1, 2, { reps: 5 }, backend)
    expect(r.queued).toBe(false)
    expect(r.set).toEqual({ id: 7, set_number: 1 })
    // The POST carried a generated client_uuid.
    const body = logSet.mock.calls[0][2] as { client_uuid?: string }
    expect(body.client_uuid).toBeTruthy()
    expect(await count(backend)).toBe(0)
  })

  it('enqueues (does not throw) when offline', async () => {
    setOnline(false)
    const logSet = vi.spyOn(api, 'logSet')
    const r = await logSetOfflineFirst(1, 2, { reps: 5 }, backend)
    expect(r.queued).toBe(true)
    expect(logSet).not.toHaveBeenCalled()
    const pending = await listPending(backend)
    expect(pending).toHaveLength(1)
    expect(pending[0].body.client_uuid).toBe(pending[0].clientUuid)
  })

  it('enqueues when the online POST fails (network blip / server down)', async () => {
    vi.spyOn(api, 'logSet').mockRejectedValue(new Error('500'))
    const r = await logSetOfflineFirst(1, 2, { reps: 5 }, backend)
    expect(r.queued).toBe(true)
    expect(await count(backend)).toBe(1)
  })
})

describe('drainQueue', () => {
  it('replays queued writes, removing each on server ack', async () => {
    setOnline(false)
    await logSetOfflineFirst(1, 2, { reps: 5 }, backend)
    await logSetOfflineFirst(1, 2, { reps: 8 }, backend)
    expect(await count(backend)).toBe(2)

    const logSet = vi.spyOn(api, 'logSet').mockResolvedValue({ id: 1 } as never)
    const res = await drainQueue(Date.now(), backend)
    expect(res.synced).toBe(2)
    expect(res.remaining).toBe(0)
    expect(logSet).toHaveBeenCalledTimes(2)
    expect(await count(backend)).toBe(0)
  })

  it('replaying an already-landed write is safe (server dedup) — still removed', async () => {
    setOnline(false)
    await logSetOfflineFirst(1, 2, { reps: 5 }, backend)
    // Server returns 2xx (its idempotent-dedup response) → treated as ack.
    vi.spyOn(api, 'logSet').mockResolvedValue({ id: 42 } as never)
    const res = await drainQueue(Date.now(), backend)
    expect(res.synced).toBe(1)
    expect(await count(backend)).toBe(0)
  })

  it('keeps a failed write and backs it off (not dropped early)', async () => {
    setOnline(false)
    await logSetOfflineFirst(1, 2, { reps: 5 }, backend)
    vi.spyOn(api, 'logSet').mockRejectedValue(new Error('503'))
    const res = await drainQueue(1_000_000, backend)
    expect(res.failed).toBe(1)
    expect(res.remaining).toBe(1)
    const [e] = await listPending(backend)
    expect(e.attempts).toBe(1)
    expect(e.nextAttemptAt).toBe(1_000_000 + 1000)
  })

  it('skips an entry still within its backoff window', async () => {
    setOnline(false)
    await logSetOfflineFirst(1, 2, { reps: 5 }, backend)
    const logSet = vi.spyOn(api, 'logSet').mockRejectedValue(new Error('503'))
    // First pass fails at t=1000000, sets nextAttemptAt=1000000+1000.
    await drainQueue(1_000_000, backend)
    logSet.mockClear()
    // A pass before the backoff elapses must not re-POST.
    const res = await drainQueue(1_000_500, backend)
    expect(logSet).not.toHaveBeenCalled()
    expect(res.synced).toBe(0)
    expect(res.remaining).toBe(1)
  })

  it('drops a write after MAX_ATTEMPTS so a poison entry cannot wedge the queue', async () => {
    setOnline(false)
    await logSetOfflineFirst(1, 2, { reps: 5 }, backend)
    vi.spyOn(api, 'logSet').mockRejectedValue(new Error('400'))
    // Force the entry to the edge of the attempt cap.
    const [e] = await listPending(backend)
    await backend.put({ ...e, attempts: 11, nextAttemptAt: 0 }) // MAX_ATTEMPTS = 12
    const res = await drainQueue(2_000_000, backend)
    expect(res.dropped).toBe(1)
    expect(await count(backend)).toBe(0)
  })
})
