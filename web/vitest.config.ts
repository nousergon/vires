import { defineConfig } from 'vitest/config'

// Standalone test config so unit tests don't load the app's build plugins
// (Tailwind / PWA). Pure-logic tests run in a node environment.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
