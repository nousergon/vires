import { api } from './api'

function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4)
  const b64 = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(b64)
  const out = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i)
  return out
}

export function pushSupported(): boolean {
  return (
    typeof navigator !== 'undefined' &&
    'serviceWorker' in navigator &&
    typeof window !== 'undefined' &&
    'PushManager' in window
  )
}

/**
 * Subscribe this device to Web Push (idempotent). Returns false if unsupported or
 * the server has no VAPID key configured (the app then falls back to the
 * foreground beep + wake-lock). Assumes Notification permission is already granted.
 */
export async function ensurePushSubscription(): Promise<boolean> {
  if (!pushSupported()) return false
  let key: string
  try {
    key = (await api.pushPublicKey()).key // 503 if server has no VAPID key
  } catch {
    return false
  }
  const reg = await navigator.serviceWorker.ready
  let sub = await reg.pushManager.getSubscription()
  if (!sub) {
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      // cast: TS 5.7 types Uint8Array as Uint8Array<ArrayBufferLike>, but
      // applicationServerKey wants a plain BufferSource.
      applicationServerKey: urlBase64ToUint8Array(key) as BufferSource,
    })
  }
  const json = sub.toJSON() as { endpoint?: string; keys?: { p256dh?: string; auth?: string } }
  if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) return false
  await api.pushSubscribe({
    endpoint: json.endpoint,
    keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
  })
  return true
}

export async function disablePush(): Promise<void> {
  if (!pushSupported()) return
  try {
    const reg = await navigator.serviceWorker.ready
    const sub = await reg.pushManager.getSubscription()
    if (sub) {
      await api.pushUnsubscribe(sub.endpoint).catch(() => {})
      await sub.unsubscribe().catch(() => {})
    }
  } catch {
    /* best-effort */
  }
}

// Best-effort scheduling — failures (e.g. push not configured) are non-fatal; the
// foreground beep still fires.
export function schedulePush(timerId: string, delaySeconds: number, title: string, body = '') {
  void api.pushSchedule(timerId, delaySeconds, title, body).catch(() => {})
}

export function cancelPush(timerId: string) {
  void api.pushCancel(timerId).catch(() => {})
}
