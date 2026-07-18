import { execSync } from 'node:child_process'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

// Build-id for the SW-independent staleness check (vires-ops#59). CI passes the
// deploy SHA as VITE_BUILD_ID; otherwise fall back to the current git short SHA
// (in CI the checkout is already at the deploy commit, so this alone is correct
// without touching the workflow), then to 'dev' when git is unavailable. Baked
// into the bundle as `__BUILD_ID__` AND written to dist/version.json, so the
// backend's /version endpoint reports the exact id the deployed bundle believes
// it is.
function resolveBuildId(): string {
  if (process.env.VITE_BUILD_ID) return process.env.VITE_BUILD_ID
  try {
    return execSync('git rev-parse --short HEAD', {
      stdio: ['ignore', 'pipe', 'ignore'],
    })
      .toString()
      .trim()
  } catch {
    return 'dev'
  }
}

const BUILD_ID = resolveBuildId()

// Emit dist/version.json at build time so the FastAPI backend has a file to
// read the deployed build-id from. Kept out of the SW precache (it's .json, not
// in Workbox's default glob) — but the client never fetches this file directly
// anyway; it fetches the backend's /version route.
function emitVersionJson(buildId: string): Plugin {
  return {
    name: 'vires-emit-version-json',
    apply: 'build',
    generateBundle() {
      this.emitFile({
        type: 'asset',
        fileName: 'version.json',
        source: `${JSON.stringify({ buildId })}\n`,
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  // The app is served under vires.nousergon.ai/app (marketing/waitlist owns the
  // domain root — a Cloudflare Worker route proxies /app* to this app's origin).
  base: '/app/',
  define: {
    // Bundle's own build-id, compared against /version at runtime (vires-ops#59).
    __BUILD_ID__: JSON.stringify(BUILD_ID),
  },
  plugins: [
    react(),
    tailwindcss(),
    emitVersionJson(BUILD_ID),
    VitePWA({
      registerType: 'autoUpdate',
      // We register the SW ourselves (App.tsx, via `virtual:pwa-register/react`)
      // so we can auto-reload an already-open tab once a new SW activates —
      // the plugin's default injected <script> just calls .register() with no
      // update/reload wiring at all, so `registerType: 'autoUpdate'` silently
      // did nothing for anyone with the PWA already open (a deploy would land
      // on the server but never reach an open tab until it was fully closed).
      injectRegister: null,
      includeAssets: ['favicon.svg', 'apple-touch-icon.png'],
      manifest: {
        name: 'Vires',
        short_name: 'Vires',
        description: 'Strength-training tracker — it gathers strength as it goes.',
        theme_color: '#0f172a',
        background_color: '#0f172a',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/app/',
        scope: '/app/',
        icons: [
          { src: '/app/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/app/icon-512.png', sizes: '512x512', type: 'image/png' },
          {
            src: '/app/icon-512-maskable.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
        // Layer our push / notificationclick handlers AND the offline set-log
        // sync drainer onto the generated SW (keeps the offline precache;
        // avoids an injectManifest migration). sync-sw.js handles the
        // Background-Sync 'sync' event for the queued-writes replay
        // (vires-ops#48) — independent of push.
        importScripts: ['/app/push-sw.js', '/app/sync-sw.js'],
        // App shell offline; API GETs cached network-first so history is
        // viewable offline (writes still need connectivity — MVP).
        // `cacheableResponse` restricts what NetworkFirst is allowed to cache
        // to real 200s — without it Workbox caches ANY response (404s, 500s,
        // opaque errors) verbatim, so a transient backend error gets served
        // back as the "offline fallback" indefinitely even after the API
        // recovers (vires-ops#40). generateSW mode only accepts this via the
        // declarative shorthand, not a constructed CacheableResponsePlugin.
        runtimeCaching: [
          {
            urlPattern: ({ url }) => url.pathname.startsWith('/app/api/'),
            handler: 'NetworkFirst',
            options: {
              cacheName: 'vires-api',
              networkTimeoutSeconds: 5,
              cacheableResponse: { statuses: [200] },
            },
          },
        ],
      },
    }),
  ],
  server: {
    proxy: {
      '/app/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/app/version': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
