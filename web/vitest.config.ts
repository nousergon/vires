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
      reporter: ['text-summary', 'lcov'],
      include: ['src/**/*.ts', 'src/**/*.tsx'],
      // Entry/bootstrap, test scaffolding + type-only files aren't unit targets.
      exclude: [
        'src/**/*.test.{ts,tsx}',
        'src/test/**',
        'src/main.tsx',
        'src/vite-env.d.ts',
      ],
    },
  },
})
