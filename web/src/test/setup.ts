import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// jsdom's localStorage isn't a usable Storage in this env (opaque origin), so
// components that persist state (WorkoutPage's active-workout id) can't run.
// Provide a minimal in-memory Storage.
class MemoryStorage implements Storage {
  private store = new Map<string, string>();
  [name: string]: unknown
  get length() {
    return this.store.size
  }
  clear() {
    this.store.clear()
  }
  getItem(k: string) {
    return this.store.has(k) ? this.store.get(k)! : null
  }
  key(i: number) {
    return [...this.store.keys()][i] ?? null
  }
  removeItem(k: string) {
    this.store.delete(k)
  }
  setItem(k: string, v: string) {
    this.store.set(k, String(v))
  }
}
// defineProperty (not vi.stubGlobal) so vi.unstubAllGlobals() in other tests
// can't wipe it.
Object.defineProperty(globalThis, 'localStorage', {
  value: new MemoryStorage(),
  configurable: true,
  writable: true,
})

afterEach(() => {
  cleanup()
  localStorage.clear()
})
