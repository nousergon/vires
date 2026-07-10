# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend enabling type-aware lint rules by installing `oxlint-tsgolint` and editing `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules) for the full list of rules and categories.

## Offline-first set logging (vires-ops#48)

Logging a set works offline. Each logged set is an immutable append keyed by a
client-generated UUID (`crypto.randomUUID()`) — **append-wins with
client-generated set UUIDs** (the settled conflict model for an append-only set
log). The write path (`src/lib/setSync.ts`, `src/lib/setQueue.ts`):

1. Mint a client UUID and attach it to the POST body.
2. **Online** → POST immediately (carrying the UUID). **Offline or POST fails**
   → durably queue the write in IndexedDB (`vires-offline` DB, `pending-sets`
   store, keyed by the UUID) and register a Background-Sync tag.
3. On reconnect the service worker's `sync` handler (`public/sync-sw.js`,
   imported into the workbox SW alongside `push-sw.js`) drains the queue —
   POSTing each pending write and removing it on a 2xx ack. The server dedupes
   on `client_uuid`, so replaying an already-landed write is a safe no-op.
4. Browsers without the Background Sync API fall back to replaying the queue on
   the `online` window event (`installOnlineReplay`, wired in `App.tsx`).

**Retry / backoff:** a failed replay is retained with bounded exponential
backoff (1s → 5min cap), dropped after `MAX_ATTEMPTS` (12) so one poison write
can't wedge the queue.

**Storage cap:** the queue is capped at `MAX_QUEUE` (500) pending writes. On
overflow it **drops the oldest** pending write and logs a `console.warn`. This
is the safer UX for a set log: the newest sets the user just performed stay
queued, and a bounded queue that sheds its stalest entry beats an unbounded one
that silently hits the IndexedDB quota and fails to persist anything.
