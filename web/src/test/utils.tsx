import type { ReactElement } from 'react'
import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import type { Settings } from '../lib/api'

/** Render a component with react-query + router providers (retries off for tests). */
export function renderWithProviders(ui: ReactElement, { route = '/' } = {}) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

export const SETTINGS: Settings = {
  weight_unit: 'lb',
  default_rest_seconds: 90,
  default_sets: 3,
  default_reps: 8,
  timer_sound: true,
  timer_vibration: true,
  timer_notification: false,
  timer_keep_awake: true,
}
