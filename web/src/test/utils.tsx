import type { ReactElement } from 'react'
import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import type {
  Exercise,
  ExerciseBrief,
  SearchHit,
  SessionExercise,
  SetEntry,
  Settings,
  Template,
  TemplateSummary,
  WorkoutSession,
} from '../lib/api'

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

// ---- typed fixture builders ----------------------------------------------- //

export function makeBrief(over: Partial<ExerciseBrief> = {}): ExerciseBrief {
  return { id: 1, name: 'Bench Press', primary_muscles: ['chest'], equipment: 'barbell', is_timed: false, ...over }
}

export function makeExercise(over: Partial<Exercise> = {}): Exercise {
  return {
    ...makeBrief(),
    secondary_muscles: [],
    mechanic: 'compound',
    category: 'strength',
    description: null,
    provenance: 'canonical',
    aliases: [],
    ...over,
  }
}

export function makeHit(over: Partial<Exercise> = {}, score = 0.9): SearchHit {
  return { exercise: makeExercise(over), score }
}

export function makeSet(over: Partial<SetEntry> = {}): SetEntry {
  return {
    id: 1000,
    set_number: 1,
    reps: 8,
    weight: 135,
    rpe: null,
    duration_seconds: null,
    is_warmup: false,
    completed_at: null,
    ...over,
  }
}

export function makeSessionExercise(over: Partial<SessionExercise> = {}): SessionExercise {
  return {
    id: 100,
    order_index: 0,
    exercise: makeBrief(),
    target_sets: 3,
    target_reps: 8,
    target_weight: 135,
    target_duration_seconds: null,
    rest_seconds: 90,
    notes: null,
    sets: [makeSet()],
    previous_performance: null,
    ...over,
  }
}

export function makeSession(over: Partial<WorkoutSession> = {}): WorkoutSession {
  return {
    id: 10,
    name: 'Push Day',
    started_at: '2026-06-28T18:00:00Z',
    ended_at: null,
    notes: null,
    template_id: null,
    exercises: [makeSessionExercise()],
    ...over,
  }
}

export function makeTemplateSummary(over: Partial<TemplateSummary> = {}): TemplateSummary {
  return { id: 1, name: 'Push Day', notes: null, exercise_count: 2, updated_at: '2026-06-20T00:00:00Z', ...over }
}

export function makeTemplate(over: Partial<Template> = {}): Template {
  return {
    id: 1,
    name: 'Push Day',
    notes: null,
    created_at: '2026-06-20T00:00:00Z',
    updated_at: '2026-06-20T00:00:00Z',
    exercises: [],
    ...over,
  }
}
