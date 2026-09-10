import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Standalone test config (no Tailwind/PWA build plugins). jsdom + Testing Library
// for component tests; pure-logic tests run fine here too.
export default defineConfig({
  plugins: [react()],
  // `__BUILD_ID__` is injected by vite.config's `define` in real builds; vitest
  // uses this config, so provide a concrete id here for the staleness tests.
  define: {
    __BUILD_ID__: JSON.stringify('test-build'),
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      // repository-baseline-policy.md §4.2 C1/C5 — the honest-scope flag for
      // the v8/vitest provider: report on every file matched by `include`,
      // not only the subset a test happened to import. Without this a
      // reported figure measures the tested subset and reports it as the
      // whole (measured on symposion: dropping the equivalent flag moved
      // 34.76% -> 92.36% with no new test code). Asserted by
      // src/test/coverage-scope.test.ts.
      all: true,
      // cobertura → genbadge can read it for the self-hosted badge.
      reporter: ['text-summary', 'lcov', 'cobertura'],
      include: ['src/**/*.ts', 'src/**/*.tsx'],
      // Entry/bootstrap, test scaffolding + type-only files aren't unit targets.
      exclude: [
        'src/**/*.test.{ts,tsx}',
        'src/test/**',
        'src/main.tsx',
        'src/vite-env.d.ts',
      ],
      // Native coverage GATE: CI fails if frontend coverage drops below these
      // floors. Ratchet — raise as component coverage grows. Raised
      // 2026-09-10 against a measured 71.27% stmts / 67.28% branches /
      // 65.35% functions / 73.36% lines (repository-baseline-policy.md §4.2
      // C3); the remainder is browser-API glue jsdom can't exercise —
      // push/recorder/wakeLock — plus the App shell.
      thresholds: {
        statements: 70,
        branches: 65,
        functions: 63,
        lines: 72,
      },
    },
  },
})
