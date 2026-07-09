import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import {
  enqueue,
  listPending,
  count,
  remove,
  clearQueue,
  markFailed,
  backoffMs,
  MAX_QUEUE,
  type PendingSet,
  type QueueBackend,
} from './setQueue'

// In-memory backend — jsdom has no usable IndexedDB, and the queue logic is
// backend-agnostic by design, so we exercise it here without a real IDB.
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

function entry(uuid: string, enqueuedAt = Date.now()): PendingSet {
  return {
    clientUuid: uuid,
    sessionId: 1,
    seId: 2,
    body: { reps: 5, client_uuid: uuid },
    enqueuedAt,
    attempts: 0,
    nextAttemptAt: 0,
  }
}

let backend: QueueBackend
beforeEach(() => {
  backend = memBackend()
})
afterEach(() => vi.restoreAllMocks())

describe('setQueue', () => {
  it('enqueues and lists oldest-first', async () => {
    await enqueue(entry('b', 200), backend)
    await enqueue(entry('a', 100), backend)
    const pending = await listPending(backend)
    expect(pending.map((p) => p.clientUuid)).toEqual(['a', 'b'])
    expect(await count(backend)).toBe(2)
  })

  it('removes and clears', async () => {
    await enqueue(entry('a'), backend)
    await enqueue(entry('b'), backend)
    await remove('a', backend)
    expect(await count(backend)).toBe(1)
    await clearQueue(backend)
    expect(await count(backend)).toBe(0)
  })

  it('put by clientUuid is idempotent (re-enqueue same UUID does not duplicate)', async () => {
    await enqueue(entry('dup', 100), backend)
    await enqueue(entry('dup', 200), backend)
    expect(await count(backend)).toBe(1)
  })

  it('caps the queue by dropping the OLDEST on overflow', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    // Fill to the cap with ascending timestamps.
    for (let i = 0; i < MAX_QUEUE; i++) {
      await enqueue(entry(`u${i}`, i), backend)
    }
    expect(await count(backend)).toBe(MAX_QUEUE)
    // One more — the newest — should evict the oldest (u0), not itself.
    await enqueue(entry('newest', MAX_QUEUE + 1), backend)
    expect(await count(backend)).toBe(MAX_QUEUE)
    const uuids = (await listPending(backend)).map((p) => p.clientUuid)
    expect(uuids).not.toContain('u0')
    expect(uuids).toContain('newest')
    expect(warn).toHaveBeenCalled()
  })

  it('backoff grows exponentially and is capped at 5min', () => {
    expect(backoffMs(1)).toBe(1000)
    expect(backoffMs(2)).toBe(2000)
    expect(backoffMs(3)).toBe(4000)
    expect(backoffMs(100)).toBe(5 * 60_000) // capped
  })

  it('markFailed bumps attempts and pushes out nextAttemptAt', async () => {
    await enqueue(entry('a'), backend)
    const [e] = await listPending(backend)
    const updated = await markFailed(e, 1_000_000, backend)
    expect(updated.attempts).toBe(1)
    expect(updated.nextAttemptAt).toBe(1_000_000 + 1000)
    const [reloaded] = await listPending(backend)
    expect(reloaded.attempts).toBe(1)
  })
})
