// Offline-first set-logging write path + replay (vires-ops#48).
//
// logSetOfflineFirst(): mint a client UUID, POST immediately when online; on
// offline OR a failed POST, park the write in IndexedDB and register a
// Background-Sync tag so the service worker drains it when connectivity
// returns. drainQueue() is the replay engine — used by the online-event
// fallback here (browsers without Background Sync) and importable by the SW.
//
// Append-wins on the client UUID (the groomer's settled ruling): the server
// dedupes on client_uuid, so replaying an already-landed write is a safe no-op.

import { api, type SetEntry } from './api'
import {
  enqueue,
  listPending,
  markFailed,
  remove,
  MAX_ATTEMPTS,
  type PendingSet,
  type QueueBackend,
} from './setQueue'

export const SYNC_TAG = 'vires-set-sync'

export interface LogSetBody {
  reps?: number | null
  weight?: number | null
  rpe?: number | null
  duration_seconds?: number | null
  is_warmup?: boolean
  done?: boolean
}

function newUuid(): string {
  // crypto.randomUUID() is available in every SW-capable browser and in Node
  // 19+/jsdom's webcrypto.
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  // crypto.getRandomValues has near-universal support (predates randomUUID by
  // a decade) — build a UUID v4 manually from it rather than falling back to
  // Math.random()/Date.now(), which is not cryptographically secure: a
  // predictable client_uuid lets one client's dedup key collide with or be
  // guessed for another's, corrupting the server-side dedup this ID exists
  // for (CodeQL js/insecure-randomness, config-I2628).
  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    const bytes = crypto.getRandomValues(new Uint8Array(16))
    bytes[6] = (bytes[6] & 0x0f) | 0x40 // version 4
    bytes[8] = (bytes[8] & 0x3f) | 0x80 // variant 10
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
  }
  throw new Error('vires: no secure random source available to mint a client_uuid')
}

function online(): boolean {
  // Treat "unknown" (no navigator) as online — the POST is the real test.
  return typeof navigator === 'undefined' || navigator.onLine !== false
}

// Ask the browser to replay the queue when it next has connectivity. Best
// effort: returns false (so the caller can fall back to the online event) when
// Background Sync is unavailable or registration fails.
export async function registerSync(): Promise<boolean> {
  try {
    if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return false
    const reg = (await navigator.serviceWorker.ready) as ServiceWorkerRegistration & {
      sync?: { register(tag: string): Promise<void> }
    }
    if (!reg.sync) return false
    await reg.sync.register(SYNC_TAG)
    return true
  } catch {
    return false
  }
}

// Log a set, offline-first. When online, POSTs immediately (carrying the UUID
// so a later manual retry is still idempotent). When offline or the POST fails,
// enqueues + registers background-sync and returns queued:true so the UI can
// show the set as pending rather than erroring.
export async function logSetOfflineFirst(
  sessionId: number,
  seId: number,
  body: LogSetBody,
  backend?: QueueBackend,
): Promise<{ queued: boolean; set?: SetEntry }> {
  const clientUuid = newUuid()
  const fullBody = { ...body, client_uuid: clientUuid }

  if (online()) {
    try {
      const set = await api.logSet(sessionId, seId, fullBody)
      return { queued: false, set }
    } catch {
      // fall through to enqueue — network blip or server down mid-session
    }
  }

  const entry: PendingSet = {
    clientUuid,
    sessionId,
    seId,
    body: fullBody,
    enqueuedAt: Date.now(),
    attempts: 0,
    nextAttemptAt: 0,
  }
  await enqueue(entry, backend)
  await registerSync()
  return { queued: true }
}

// Replay every due pending write. Returns counts for logging/observability.
// - success (2xx, incl. the server's idempotent-dedup response) → remove entry
// - failure → bounded exponential backoff via markFailed; drop once MAX_ATTEMPTS
//   is exhausted so a permanently-rejected write can't wedge the queue.
// Entries whose nextAttemptAt is in the future are skipped this pass.
export async function drainQueue(
  now: number = Date.now(),
  backend?: QueueBackend,
): Promise<{ synced: number; failed: number; dropped: number; remaining: number }> {
  const pending = await listPending(backend)
  let synced = 0
  let failed = 0
  let dropped = 0

  for (const entry of pending) {
    if (entry.nextAttemptAt > now) continue // backing off
    try {
      await api.logSet(entry.sessionId, entry.seId, entry.body)
      await remove(entry.clientUuid, backend)
      synced++
    } catch {
      const updated = await markFailed(entry, now, backend)
      if (updated.attempts >= MAX_ATTEMPTS) {
        await remove(entry.clientUuid, backend)
        dropped++
        console.warn(
          `[vires] dropping set ${entry.clientUuid} after ${updated.attempts} failed sync attempts`,
        )
      } else {
        failed++
      }
    }
  }

  const remaining = (await listPending(backend)).length
  return { synced, failed, dropped, remaining }
}

// Fallback for browsers without the Background Sync API: replay the queue when
// the tab regains connectivity. Idempotent to attach; call once at startup.
let onlineListenerAttached = false
export function installOnlineReplay(): void {
  if (onlineListenerAttached) return
  if (typeof window === 'undefined' || typeof window.addEventListener !== 'function') return
  onlineListenerAttached = true
  window.addEventListener('online', () => {
    void drainQueue().catch(() => {})
  })
}

// Test-only reset so the listener guard doesn't leak across test files.
export function _resetOnlineReplayForTests(): void {
  onlineListenerAttached = false
}
