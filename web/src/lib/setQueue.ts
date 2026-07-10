// Durable, offline-first queue of pending set-log writes (vires-ops#48).
//
// DESIGN — append-wins with client-generated set UUIDs (the groomer's settled
// ruling): every logged set is an immutable append keyed by a client-minted
// `crypto.randomUUID()`. While offline (or when an online POST fails) the write
// is parked here in IndexedDB; on reconnect the service worker / online-event
// fallback replays each entry, and the server dedupes on the UUID so a replay
// is idempotent (near-conflict-free by construction for an append-only log).
//
// The store is abstracted behind a tiny async KV `QueueBackend` so the same
// logic runs on real IndexedDB in the browser AND on an in-memory backend under
// Vitest/jsdom (which has no usable IndexedDB). Nothing here touches the DOM.

export interface PendingSet {
  // Client-generated UUID — the primary key AND the server-side dedup key.
  clientUuid: string
  // Where the set belongs. Recorded at enqueue time from the live session.
  sessionId: number
  seId: number
  // The POST body (already in the account's display units, matching api.logSet).
  body: {
    reps?: number | null
    weight?: number | null
    rpe?: number | null
    duration_seconds?: number | null
    is_warmup?: boolean
    done?: boolean
    client_uuid: string
  }
  // Bookkeeping for bounded retry/backoff and drop-oldest eviction.
  enqueuedAt: number
  attempts: number
  // Epoch ms before which a failed entry should not be retried (backoff).
  nextAttemptAt: number
}

// Minimal async key/value surface the queue needs. Keys are clientUuid.
export interface QueueBackend {
  getAll(): Promise<PendingSet[]>
  put(entry: PendingSet): Promise<void>
  delete(clientUuid: string): Promise<void>
  clear(): Promise<void>
}

export const DB_NAME = 'vires-offline'
export const STORE_NAME = 'pending-sets'
export const DB_VERSION = 1

// Cap the queue so a long offline stretch (or a stuck server) can't grow
// IndexedDB without bound. On overflow we DROP THE OLDEST pending write and
// surface a warning — the safer UX for a set log: the newest sets the user just
// performed are the ones they still see unsynced, and an unbounded queue that
// silently fails to persist (quota exceeded) is worse than a bounded one that
// tells you it shed the stalest entry. Documented in web/README.md.
export const MAX_QUEUE = 500

// ---- IndexedDB backend (browser) ------------------------------------------ //
function idbSupported(): boolean {
  return typeof indexedDB !== 'undefined'
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'clientUuid' })
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

function tx<T>(mode: IDBTransactionMode, run: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return openDb().then(
    (db) =>
      new Promise<T>((resolve, reject) => {
        const t = db.transaction(STORE_NAME, mode)
        const store = t.objectStore(STORE_NAME)
        const req = run(store)
        t.oncomplete = () => {
          db.close()
          resolve(req.result)
        }
        t.onerror = () => {
          db.close()
          reject(t.error)
        }
      }),
  )
}

export const idbBackend: QueueBackend = {
  getAll: () => tx('readonly', (s) => s.getAll() as IDBRequest<PendingSet[]>),
  put: (entry) => tx('readwrite', (s) => s.put(entry)).then(() => undefined),
  delete: (clientUuid) => tx('readwrite', (s) => s.delete(clientUuid)).then(() => undefined),
  clear: () => tx('readwrite', (s) => s.clear()).then(() => undefined),
}

// ---- queue operations (backend-agnostic) ---------------------------------- //
export function defaultBackend(): QueueBackend {
  return idbBackend
}

export async function enqueue(
  entry: PendingSet,
  backend: QueueBackend = defaultBackend(),
): Promise<void> {
  await backend.put(entry)
  // Enforce the cap AFTER the put so the just-added (newest) entry is never the
  // one evicted. Drop the oldest by enqueuedAt.
  const all = await backend.getAll()
  if (all.length > MAX_QUEUE) {
    const overflow = all
      .slice()
      .sort((a, b) => a.enqueuedAt - b.enqueuedAt)
      .slice(0, all.length - MAX_QUEUE)
    for (const old of overflow) {
      await backend.delete(old.clientUuid)
      console.warn(
        `[vires] offline set-log queue over ${MAX_QUEUE}; dropped oldest pending set ${old.clientUuid}`,
      )
    }
  }
}

export async function listPending(backend: QueueBackend = defaultBackend()): Promise<PendingSet[]> {
  const all = await backend.getAll()
  // Oldest first — replay in the order the user logged them.
  return all.slice().sort((a, b) => a.enqueuedAt - b.enqueuedAt)
}

export async function count(backend: QueueBackend = defaultBackend()): Promise<number> {
  return (await backend.getAll()).length
}

export async function remove(
  clientUuid: string,
  backend: QueueBackend = defaultBackend(),
): Promise<void> {
  await backend.delete(clientUuid)
}

export async function clearQueue(backend: QueueBackend = defaultBackend()): Promise<void> {
  await backend.clear()
}

// Bounded exponential backoff for a failed replay: 1s, 2s, 4s … capped at 5min.
// Also caps total attempts so a permanently-rejected write can't wedge the
// queue forever — after MAX_ATTEMPTS the entry is dropped by the drainer.
export const MAX_ATTEMPTS = 12
const BASE_BACKOFF_MS = 1000
const MAX_BACKOFF_MS = 5 * 60_000

export function backoffMs(attempts: number): number {
  return Math.min(BASE_BACKOFF_MS * 2 ** Math.max(0, attempts - 1), MAX_BACKOFF_MS)
}

// Record a failed attempt: bump the counter and push out nextAttemptAt. Returns
// the updated entry (persisted). The caller decides whether MAX_ATTEMPTS is hit.
export async function markFailed(
  entry: PendingSet,
  now: number = Date.now(),
  backend: QueueBackend = defaultBackend(),
): Promise<PendingSet> {
  const updated: PendingSet = {
    ...entry,
    attempts: entry.attempts + 1,
    nextAttemptAt: now + backoffMs(entry.attempts + 1),
  }
  await backend.put(updated)
  return updated
}

export function isSupported(): boolean {
  return idbSupported()
}
