// Typed client for the Vires API. Same-origin in production; the Vite dev
// server proxies /api -> FastAPI (see vite.config.ts).

const BASE = '/api'

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* non-JSON error body */
    }
    throw new Error(`${res.status}: ${detail}`)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

// ---- types ---------------------------------------------------------------- //
export interface ExerciseBrief {
  id: number
  name: string
  primary_muscles: string[]
  equipment: string | null
  is_timed: boolean
}

export interface Exercise extends ExerciseBrief {
  secondary_muscles: string[]
  mechanic: string | null
  category: string | null
  description: string | null
  provenance: string
  aliases: string[]
}

export interface SearchHit {
  exercise: Exercise
  score: number
}

export interface CreateResult {
  created: boolean
  reason: 'created' | 'exact' | 'similar'
  exercise: Exercise | null
  duplicate_of: Exercise | null
  similarity: number | null
}

export interface PerformedSet {
  set_number: number
  reps: number | null
  weight: number | null
  rpe: number | null
  is_warmup: boolean
}

export interface ExercisePerformance {
  session_id: number
  session_name: string | null
  date: string
  sets: PerformedSet[]
}

export interface SetEntry {
  id: number
  set_number: number
  reps: number | null
  weight: number | null
  rpe: number | null
  duration_seconds: number | null
  is_warmup: boolean
  completed_at: string | null
}

export interface SessionExercise {
  id: number
  order_index: number
  exercise: ExerciseBrief
  target_sets: number | null
  target_reps: number | null
  target_weight: number | null
  target_duration_seconds: number | null
  rest_seconds: number | null
  notes: string | null
  sets: SetEntry[]
  previous_performance: ExercisePerformance | null
}

export interface WorkoutSession {
  id: number
  name: string | null
  started_at: string
  ended_at: string | null
  notes: string | null
  template_id: number | null
  exercises: SessionExercise[]
}

export interface WorkoutSummary {
  id: number
  name: string | null
  started_at: string
  ended_at: string | null
  exercise_count: number
  set_count: number
  total_volume: number
}

export interface TemplateExercise {
  id: number
  order_index: number
  exercise: ExerciseBrief
  target_sets: number | null
  target_reps: number | null
  target_weight: number | null
  target_duration_seconds: number | null
  rest_seconds: number | null
  notes: string | null
}

export interface Template {
  id: number
  name: string
  notes: string | null
  created_at: string
  updated_at: string
  exercises: TemplateExercise[]
}

export interface TemplateSummary {
  id: number
  name: string
  notes: string | null
  exercise_count: number
  updated_at: string
}

export interface TemplateExerciseInput {
  exercise_id: number
  target_sets?: number | null
  target_reps?: number | null
  target_weight?: number | null
  target_duration_seconds?: number | null
  rest_seconds?: number | null
  notes?: string | null
}

export type WeightUnit = 'lb' | 'kg'

export interface Settings {
  weight_unit: WeightUnit
  default_rest_seconds: number
  default_sets: number
  default_reps: number
}

// ---- personal records ----------------------------------------------------- //
export type RecordWindow = 'all' | 'year' | 'quarter' | 'month'

export interface RecordMetric {
  value: number
  weight: number | null
  reps: number | null
  date: string
}

export interface ExerciseRecords {
  exercise: ExerciseBrief
  is_timed: boolean
  est_1rm: RecordMetric | null
  heaviest: RecordMetric | null
  best_set_volume: RecordMetric | null
  most_reps: RecordMetric | null
  longest_hold: RecordMetric | null
}

// ---- plan / calendar / coach ---------------------------------------------- //
export interface CalendarEntry {
  kind: 'session' | 'planned'
  date: string // YYYY-MM-DD
  id: number
  name: string | null
  status: string
  program_id: number | null
  template_id: number | null
  exercise_count: number
  session_id: number | null
}

export interface PlannedExercise {
  id: number
  order_index: number
  exercise: ExerciseBrief
  target_sets: number | null
  target_reps: number | null
  target_weight: number | null
  target_duration_seconds: number | null
  rest_seconds: number | null
  notes: string | null
}

export interface PlannedWorkout {
  id: number
  program_id: number | null
  template_id: number | null
  scheduled_date: string
  name: string
  notes: string | null
  week_index: number | null
  status: string
  created_by: string
  session_id: number | null
  exercises: PlannedExercise[]
}

// The coach's declarative spec — resent verbatim for a refine turn.
export interface ProgressionCurve {
  mode: string
  start: number
  end: number
  steps?: number | null
}
export interface ExerciseProgression {
  template_id: number
  exercise_id?: number | null
  sets?: number | null
  reps?: ProgressionCurve | null
  weight?: ProgressionCurve | null
  seed_weight?: number | null
}
export interface ScheduleEntry {
  template_id: number
  weekday: number
}
export interface ProgramSpec {
  name: string
  start_date: string
  duration_weeks: number
  schedule: ScheduleEntry[]
  progressions: ExerciseProgression[]
  deload_weeks: number[]
  coach_summary: string
}

export interface PlannedExercisePreview {
  exercise_id: number
  exercise_name: string
  order_index: number
  target_sets: number | null
  target_reps: number | null
  target_weight: number | null
  target_duration_seconds: number | null
  rest_seconds: number | null
  notes: string | null
}
export interface PlannedWorkoutPreview {
  template_id: number | null
  scheduled_date: string
  name: string
  week_index: number | null
  exercises: PlannedExercisePreview[]
}
export interface ProgramPreview {
  name: string
  coach_summary: string
  start_date: string
  end_date: string
  weight_unit: string
  spec: ProgramSpec
  planned_workouts: PlannedWorkoutPreview[]
}

export interface ProgramSummary {
  id: number
  name: string
  goal_text: string | null
  start_date: string | null
  end_date: string | null
  status: string
  planned_count: number
  completed_count: number
}

// ---- endpoints ------------------------------------------------------------ //
export const api = {
  // exercises
  searchExercises: (q: string, limit = 25) =>
    req<SearchHit[]>(`/exercises/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  createExercise: (body: {
    name: string
    primary_muscles?: string[]
    equipment?: string | null
    force?: boolean
  }) => req<CreateResult>('/exercises', { method: 'POST', body: JSON.stringify(body) }),
  exerciseHistory: (id: number) => req<ExercisePerformance[]>(`/exercises/${id}/history`),

  // templates
  listTemplates: () => req<TemplateSummary[]>('/templates'),
  getTemplate: (id: number) => req<Template>(`/templates/${id}`),
  createTemplate: (body: { name: string; notes?: string; exercises: TemplateExerciseInput[] }) =>
    req<Template>('/templates', { method: 'POST', body: JSON.stringify(body) }),
  updateTemplate: (
    id: number,
    body: { name?: string; notes?: string; exercises?: TemplateExerciseInput[] },
  ) => req<Template>(`/templates/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteTemplate: (id: number) => req<void>(`/templates/${id}`, { method: 'DELETE' }),

  // workouts
  startWorkout: (body: { template_id?: number | null; name?: string | null }) =>
    req<WorkoutSession>('/workouts', { method: 'POST', body: JSON.stringify(body) }),
  listWorkouts: () => req<WorkoutSummary[]>('/workouts'),
  getWorkout: (id: number) => req<WorkoutSession>(`/workouts/${id}`),
  finishWorkout: (id: number) => req<WorkoutSession>(`/workouts/${id}/finish`, { method: 'POST' }),
  deleteWorkout: (id: number) => req<void>(`/workouts/${id}`, { method: 'DELETE' }),
  addWorkoutExercise: (sessionId: number, body: TemplateExerciseInput) =>
    req<SessionExercise>(`/workouts/${sessionId}/exercises`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  removeWorkoutExercise: (sessionId: number, seId: number) =>
    req<void>(`/workouts/${sessionId}/exercises/${seId}`, { method: 'DELETE' }),
  logSet: (
    sessionId: number,
    seId: number,
    body: {
      reps?: number | null
      weight?: number | null
      rpe?: number | null
      duration_seconds?: number | null
      is_warmup?: boolean
    },
  ) =>
    req<SetEntry>(`/workouts/${sessionId}/exercises/${seId}/sets`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateSet: (
    sessionId: number,
    seId: number,
    setId: number,
    body: Partial<{
      reps: number
      weight: number
      rpe: number
      duration_seconds: number
      is_warmup: boolean
      done: boolean
    }>,
  ) =>
    req<SetEntry>(`/workouts/${sessionId}/exercises/${seId}/sets/${setId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteSet: (sessionId: number, seId: number, setId: number) =>
    req<void>(`/workouts/${sessionId}/exercises/${seId}/sets/${setId}`, { method: 'DELETE' }),

  // settings
  getSettings: () => req<Settings>('/settings'),
  updateSettings: (body: Partial<Settings>) =>
    req<Settings>('/settings', { method: 'PUT', body: JSON.stringify(body) }),

  // records
  records: (window: RecordWindow) => req<ExerciseRecords[]>(`/records?window=${window}`),

  // plan / calendar
  calendar: (start: string, end: string) =>
    req<CalendarEntry[]>(`/plan/calendar?start=${start}&end=${end}`),
  getPlanned: (id: number) => req<PlannedWorkout>(`/plan/planned/${id}`),
  createPlanned: (body: {
    scheduled_date: string
    template_id?: number | null
    name?: string | null
    notes?: string | null
  }) => req<PlannedWorkout>('/plan/planned', { method: 'POST', body: JSON.stringify(body) }),
  updatePlanned: (
    id: number,
    body: Partial<{ scheduled_date: string; name: string; notes: string; status: string }>,
  ) => req<PlannedWorkout>(`/plan/planned/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deletePlanned: (id: number) => req<void>(`/plan/planned/${id}`, { method: 'DELETE' }),
  startPlanned: (id: number) =>
    req<WorkoutSession>(`/plan/planned/${id}/start`, { method: 'POST' }),
  listPrograms: () => req<ProgramSummary[]>('/plan/programs'),
  deleteProgram: (id: number) => req<void>(`/plan/programs/${id}`, { method: 'DELETE' }),

  // coach
  coachGenerate: (message: string, priorSpec?: ProgramSpec) =>
    req<ProgramPreview>('/coach/generate', {
      method: 'POST',
      body: JSON.stringify({ message, prior_spec: priorSpec ?? null }),
    }),
  coachSaveProgram: (spec: ProgramSpec, name?: string, goalText?: string) =>
    req<{ id: number; name: string }>('/coach/programs', {
      method: 'POST',
      body: JSON.stringify({ spec, name: name ?? null, goal_text: goalText ?? null }),
    }),
}
