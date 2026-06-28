import { defineConfig } from 'vitest/config'

// Standalone test config so unit tests don't load the app's build plugins
// (Tailwind / PWA). Pure-logic tests run in a node environment.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text-summary', 'lcov'],
      include: ['src/**/*.ts', 'src/**/*.tsx'],
      // Entry/bootstrap + type-only files aren't unit-test targets.
      exclude: ['src/**/*.test.ts', 'src/main.tsx', 'src/vite-env.d.ts'],
    },
  },
})
