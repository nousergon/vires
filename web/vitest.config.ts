import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Standalone test config (no Tailwind/PWA build plugins). jsdom + Testing Library
// for component tests; pure-logic tests run fine here too.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
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
      // floors. Ratchet — raise as component coverage grows (currently ~26%).
      thresholds: {
        statements: 20,
        branches: 20,
        functions: 20,
        lines: 20,
      },
    },
  },
})
