/* eslint-disable */
// Imported into the workbox-generated service worker (vite.config →
// workbox.importScripts). Shows the timer-end notification pushed by the server
// when the app is backgrounded/locked, and focuses the app when tapped.
self.addEventListener('push', (event) => {
  let data = {}
  try {
    data = event.data ? event.data.json() : {}
  } catch (e) {
    /* non-JSON payload */
  }
  const title = data.title || 'Vires'
  event.waitUntil(
    self.registration.showNotification(title, {
      body: data.body || '',
      tag: 'vires-timer',
      renotify: true,
      // Buzz on the locked screen too, so an end-of-timer alert reaches the
      // user out of the app (the in-app beep/vibrate can't fire backgrounded).
      vibrate: [120, 60, 120],
      icon: '/icon-192.png',
      badge: '/icon-192.png',
    }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      for (const client of list) {
        if ('focus' in client) return client.focus()
      }
      if (self.clients.openWindow) return self.clients.openWindow('/app/train')
    }),
  )
})
