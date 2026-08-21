import type { ReactElement } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import type {
  ActiveObjective,
  ActivityDetail,
  Exercise,
  ExerciseBrief,
  Objective,
  SearchHit,
  SessionExercise,
  SetEntry,
  Settings,
  Template,
  TemplateSummary,
  WorkoutSession,
} from '../lib/api'

/**
 * Click a button by its accessible name, after waiting for it to be ENABLED.
 *
 * Why this exists (vires-ops#77). `fireEvent.click` on a `disabled` button is a
 * SILENT no-op: React does not fire `onClick`, nothing throws, and the
 * assertion that follows fails as "the handler was never called" — which reads
 * as a product defect rather than a test that acted too early. That is exactly
 * how `ObjectiveSheet.test.tsx` failed on CI's Node 20 while passing on newer
 * Node locally: the test waited for the NAME field to prefill and then clicked
 * a button whose `disabled` is derived from several other pieces of state, so
 * "the form is populated" and "the button is clickable" are not the same event
 * and their order is not guaranteed.
 *
 * Two properties, both load-bearing:
 *
 * 1. It waits for the button to be enabled, so the click cannot land early.
 * 2. It ASSERTS the button is enabled rather than clicking regardless — a
 *    button that never enables fails here, naming the button, instead of
 *    failing later as an uncalled mock.
 *
 * Prefer this over `fireEvent.click(screen.getByText(...))` anywhere the target
 * is a button whose `disabled` is computed. Sweep of the remaining call sites
 * is tracked on vires-ops#77.
 */
export async function clickEnabledButton(name: string | RegExp) {
  const button = await screen.findByRole('button', { name })
  await waitFor(() => {
    if ((button as HTMLButtonElement).disabled) {
      throw new Error(
        `button "${String(name)}" is still disabled — the click would be a silent no-op`,
      )
    }
  })
  fireEvent.click(button)
  return button
}

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
  preferred_weekdays: [],
}

// ---- typed fixture builders ----------------------------------------------- //

export function makeBrief(over: Partial<ExerciseBrief> = {}): ExerciseBrief {
  return {
    id: 1,
    name: 'Bench Press',
    primary_muscles: ['chest'],
    equipment: 'barbell',
    is_timed: false,
    movement_pattern: 'horizontal_push',
    ...over,
  }
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

export function makeActivityDetail(over: Partial<ActivityDetail> = {}): ActivityDetail {
  return {
    template_key: 'custom',
    duration_s: 1800,
    regions: 'full',
    intensity: 'moderate',
    pack_weight_kg: null,
    bodyweight_kg: null,
    distance_m: null,
    elevation_gain_m: null,
    terrain: 'trail',
    metabolic_cost_kj: null,
    source: 'manual',
    sport: null,
    event_end_date: null,
    recurrence: 'none',
    objective_id: null,
    ...over,
  }
}

export function makeSession(over: Partial<WorkoutSession> = {}): WorkoutSession {
  return {
    id: 10,
    session_type: 'strength',
    name: 'Push Day',
    started_at: '2026-06-28T18:00:00Z',
    ended_at: null,
    notes: null,
    tags: [],
    energy_level: null,
    workout_intensity: null,
    challenge_level: null,
    template_id: null,
    exercises: [makeSessionExercise()],
    activity: null,
    recurrence_source_id: null,
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
    swap_feedback: [],
    ...over,
  }
}

export function makeObjective(over: Partial<Objective> = {}): Objective {
  return {
    id: 1,
    name: 'Climb Baker',
    kind: 'dated',
    target_date: '2026-09-05',
    event_end_date: null,
    sport: 'alpine',
    demands_profile: null,
    is_primary: true,
    priority: 0,
    parent_objective_id: null,
    created_at: '',
    updated_at: '',
    ...over,
  }
}

export function makeActiveObjective(over: Partial<ActiveObjective> = {}): ActiveObjective {
  const objective = over.objective ?? null
  return {
    objective,
    // Default the top-level list to the focus objective (if any) unless overridden.
    objectives: objective ? [objective] : [],
    milestones: [],
    constraints: [],
    active_program: null,
    ...over,
  }
}
