/* eslint-disable */
// Offline-first set-log sync (vires-ops#48). Imported into the workbox-generated
// service worker alongside push-sw.js (see vite.config → workbox.importScripts);
// it does NOT touch push. Drains the IndexedDB queue of pending set-log writes
// on a Background-Sync 'sync' event (registered by the page on offline/failed
// writes), POSTing each and removing it on a server ack. The server dedupes on
// the client-generated set UUID, so a replay of an already-landed write is a
// safe no-op (append-wins on client UUID — the groomer's settled ruling).
//
// This file is plain JS loaded into the SW global scope (importScripts), so it
// re-declares the store constants rather than importing the TS queue module.
// They MUST stay in sync with web/src/lib/setQueue.ts.

const SYNC_TAG = 'vires-set-sync'
const DB_NAME = 'vires-offline'
const STORE_NAME = 'pending-sets'
const DB_VERSION = 1
const MAX_ATTEMPTS = 12
const BASE_BACKOFF_MS = 1000
const MAX_BACKOFF_MS = 5 * 60 * 1000

function openDb() {
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

function idbGetAll(db) {
  return new Promise((resolve, reject) => {
    const req = db.transaction(STORE_NAME, 'readonly').objectStore(STORE_NAME).getAll()
    req.onsuccess = () => resolve(req.result || [])
    req.onerror = () => reject(req.error)
  })
}

function idbPut(db, entry) {
  return new Promise((resolve, reject) => {
    const t = db.transaction(STORE_NAME, 'readwrite')
    t.objectStore(STORE_NAME).put(entry)
    t.oncomplete = () => resolve()
    t.onerror = () => reject(t.error)
  })
}

function idbDelete(db, key) {
  return new Promise((resolve, reject) => {
    const t = db.transaction(STORE_NAME, 'readwrite')
    t.objectStore(STORE_NAME).delete(key)
    t.oncomplete = () => resolve()
    t.onerror = () => reject(t.error)
  })
}

function backoffMs(attempts) {
  return Math.min(BASE_BACKOFF_MS * Math.pow(2, Math.max(0, attempts - 1)), MAX_BACKOFF_MS)
}

async function drainQueue() {
  const db = await openDb()
  const now = Date.now()
  const pending = (await idbGetAll(db)).sort((a, b) => a.enqueuedAt - b.enqueuedAt)
  let requeued = false

  for (const entry of pending) {
    if ((entry.nextAttemptAt || 0) > now) {
      requeued = true // still backing off — need another pass later
      continue
    }
    try {
      const res = await fetch(
        `/api/workouts/${entry.sessionId}/exercises/${entry.seId}/sets`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(entry.body),
        },
      )
      // 2xx (incl. the server's idempotent-dedup 201) = acked → drop.
      // A 4xx that isn't a transient auth blip is unrecoverable — drop it too so
      // one poison write can't wedge the queue (mirrors MAX_ATTEMPTS below).
      if (res.ok) {
        await idbDelete(db, entry.clientUuid)
      } else if (res.status >= 400 && res.status < 500 && res.status !== 408 && res.status !== 429) {
        await idbDelete(db, entry.clientUuid)
      } else {
        throw new Error(`HTTP ${res.status}`)
      }
    } catch (e) {
      const attempts = (entry.attempts || 0) + 1
      if (attempts >= MAX_ATTEMPTS) {
        await idbDelete(db, entry.clientUuid)
      } else {
        await idbPut(db, {
          ...entry,
          attempts,
          nextAttemptAt: now + backoffMs(attempts),
        })
        requeued = true
      }
    }
  }

  db.close()
  // Reject so the browser reschedules the sync when entries remain (backing off
  // or transiently failed). A resolved handler means "done, don't retry".
  if (requeued) throw new Error('vires-set-sync: entries remain, retry later')
}

self.addEventListener('sync', (event) => {
  if (event.tag === SYNC_TAG) {
    event.waitUntil(drainQueue())
  }
})

// Let the page nudge a drain (e.g. the online-event fallback) via postMessage.
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'vires-drain-sets') {
    event.waitUntil(drainQueue().catch(() => {}))
  }
})
