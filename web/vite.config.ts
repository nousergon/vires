import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'apple-touch-icon.png'],
      manifest: {
        name: 'Vires',
        short_name: 'Vires',
        description: 'Strength-training tracker — it gathers strength as it goes.',
        theme_color: '#0f172a',
        background_color: '#0f172a',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/',
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
          {
            src: '/icon-512-maskable.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
        // Layer our push / notificationclick handlers onto the generated SW
        // (keeps the offline precache; avoids an injectManifest migration).
        importScripts: ['/push-sw.js'],
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
            urlPattern: ({ url }) => url.pathname.startsWith('/api/'),
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
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
