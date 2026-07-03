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
  reason: 'created' | 'exact'
  exercise: Exercise | null
  duplicate_of: Exercise | null
  // Non-blocking "similar exercise" hint, set alongside a successful create.
  similar_to: Exercise | null
  similar_to_similarity: number | null
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

export type SessionType = 'strength' | 'activity'

export type Terrain = 'treadmill' | 'road' | 'trail' | 'offtrail' | 'snow'

export type RouteSource = 'manual' | 'route_search' | 'route_draw' | 'gpx'

export type LoadRegions = 'legs' | 'upper' | 'full' | 'core' | 'none'
export type LoadIntensity = 'light' | 'moderate' | 'hard'
// 'weekly' repeats every 7 days from the activity's own started_at date,
// expanded server-side on read — never persisted as extra rows.
export type Recurrence = 'none' | 'weekly'

// One entry in the fixed activity-template catalog (GET /workouts/activity-templates).
// route_capable templates (walk/run/hike) additionally get the route-capture
// UI + an optional pack-weight section. The last five entries (race,
// league_game, recreation_event, trip, rehab_window) are what used to
// require a separate CalendarEvent — see ActivityForm's future/recurring
// section, shown based purely on the chosen date, never on which template
// is picked.
export interface ActivityTemplate {
  key: string
  label: string
  regions: LoadRegions
  intensity: LoadIntensity
  route_capable: boolean
}

// Canonical SI (the API stores/returns SI; the UI converts for display).
// pack_weight_kg/bodyweight_kg/distance_m/elevation_gain_m/metabolic_cost_kj
// are only ever set on a route_capable template logged with that data.
export interface ActivityDetail {
  template_key: string
  duration_s: number | null
  regions: LoadRegions
  intensity: LoadIntensity
  pack_weight_kg: number | null
  bodyweight_kg: number | null
  distance_m: number | null
  elevation_gain_m: number | null
  terrain: string
  metabolic_cost_kj: number | null
  source: string
  // Former CalendarEvent axes — merged in so a future/recurring/multi-day/
  // objective-anchored activity is the SAME row type as a logged one; there
  // is no separate "planned" flag, only started_at/ended_at vs. now.
  sport: string | null
  event_end_date: string | null
  recurrence: Recurrence
  objective_id: number | null
}

// Quick-log / create payload — numbers in the account's DISPLAY units
// (server converts). A future started_at with no other event fields is a
// plain "planned activity"; recurrence/event_end_date/objective_id are the
// event-only axes (formerly a separate CalendarEvent create).
export interface ActivityLogInput {
  name: string
  template_key?: string
  duration_s?: number | null
  regions: LoadRegions
  intensity: LoadIntensity
  // ISO datetime — omit to default to now server-side; set to backdate OR
  // future-date (a future date leaves ended_at null server-side).
  started_at?: string | null
  // Route capture — optional for every template.
  distance?: number | null
  elevation_gain?: number | null
  terrain?: Terrain
  source?: RouteSource
  // Load-carriage — never required. bodyweight is required IFF pack_weight
  // is given (server-validated).
  pack_weight?: number | null
  bodyweight?: number | null
  // Event-merge fields.
  sport?: string | null
  recurrence?: Recurrence
  event_end_date?: string | null
  objective_id?: number | null
}

// Partial update to a session (PATCH /workouts/{id}) — edits a still-open
// future/planned activity, OR closes one out by including ended_at ("log
// what actually happened"). Only send the fields you're changing.
export interface WorkoutSessionUpdate {
  name?: string
  started_at?: string
  ended_at?: string
  notes?: string | null
  // Session-tracking fields — valid on any session type. `tags` replaces the
  // whole list; the 1–10 ratings can be revised after finishing.
  tags?: string[]
  pre_workout_fuel?: string | null
  energy_level?: number | null
  workout_intensity?: number | null
  template_key?: string
  duration_s?: number | null
  regions?: LoadRegions
  intensity?: LoadIntensity
  distance?: number | null
  elevation_gain?: number | null
  terrain?: Terrain
  source?: RouteSource
  pack_weight?: number | null
  bodyweight?: number | null
  sport?: string | null
  recurrence?: Recurrence
  event_end_date?: string | null
  objective_id?: number | null
}

// ---- route derivation (trail search / draw / GPX) ------------------------- //
export interface RoutePoint {
  lat: number
  lon: number
  ele_m?: number | null
}

// Canonical SI route stats (the UI converts to display units to prefill fields).
export interface RouteStats {
  distance_m: number
  elevation_gain_m: number | null
  point_count: number
  duration_s: number | null
}

export interface TrailCandidate {
  osm_id: number
  name: string
  distance_m: number
  points: RoutePoint[]
}

export interface WorkoutSession {
  id: number
  session_type: SessionType
  name: string | null
  started_at: string
  ended_at: string | null
  notes: string | null
  // Free-text labels (reusable tags + one-off custom inputs).
  tags: string[]
  // Pre-workout food/drink/supplements, free text.
  pre_workout_fuel: string | null
  // End-of-workout 1–10 self-report (null until finished with a rating).
  energy_level: number | null
  workout_intensity: number | null
  template_id: number | null
  exercises: SessionExercise[]
  activity: ActivityDetail | null
  // Set only on a materialized occurrence of a recurring activity — the id
  // of the recurring "template" session it was expanded from.
  recurrence_source_id: number | null
}

export interface WorkoutSummary {
  id: number
  session_type: SessionType
  name: string | null
  started_at: string
  ended_at: string | null
  exercise_count: number
  set_count: number
  total_volume: number
  tags: string[]
  energy_level: number | null
  workout_intensity: number | null
  activity: ActivityDetail | null
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
  timer_sound: boolean
  timer_vibration: boolean
  timer_notification: boolean
  timer_keep_awake: boolean
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
  kind: 'session' | 'planned' | 'objective' | 'objective_block'
  date: string // YYYY-MM-DD
  id: number
  name: string | null
  // session: completed|in_progress|upcoming; planned: planned|completed|skipped;
  // objective: peak|event; objective_block: block
  status: string
  program_id?: number | null
  template_id?: number | null
  objective_id?: number | null
  objective_name?: string | null
  exercise_count: number
  session_id?: number | null
  // planned only: set when the coach auto-moved this day forward because it
  // was missed — the date it moved FROM.
  rescheduled_from?: string | null
  // session only: distinguishes a lift from a logged/planned activity.
  session_type?: SessionType | null
  // session only: True for a synthesized weekly occurrence with no row of
  // its own yet. `id` is the recurring template session's real id — pair
  // with `date` to materializeOccurrence() it.
  virtual?: boolean
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
  // Set when the coach auto-moved this day forward because it was missed —
  // the date it moved FROM.
  rescheduled_from: string | null
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
  template_id?: number | null
  routine_key?: string | null
  exercise_id?: number | null
  sets?: number | null
  reps?: ProgressionCurve | null
  weight?: ProgressionCurve | null
  seed_weight?: number | null
}
export interface ScheduleEntry {
  template_id?: number | null
  routine_key?: string | null
  weekday: string // lowercase day name, e.g. 'monday'
}
// A routine the coach authors for the objective (persisted on save).
export interface RoutineExerciseSpec {
  exercise_id: number
  sets?: number | null
  reps?: number | null
  weight?: number | null
  duration_seconds?: number | null
  rest_seconds?: number | null
}
export interface RoutineSpec {
  key: string
  name: string
  exercises: RoutineExerciseSpec[]
}
export interface ProgramSpec {
  name: string
  start_date: string
  duration_weeks: number
  new_routines: RoutineSpec[]
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
export interface CreatedRoutinePreview {
  key: string
  name: string
  exercise_names: string[]
}
export interface ProgramPreview {
  name: string
  coach_summary: string
  start_date: string
  end_date: string
  weight_unit: string
  spec: ProgramSpec
  planned_workouts: PlannedWorkoutPreview[]
  created_routines: CreatedRoutinePreview[]
}

export interface ProgramSummary {
  id: number
  name: string
  goal_text: string | null
  coach_summary: string | null
  objective_id: number | null
  start_date: string | null
  end_date: string | null
  status: string
  planned_count: number
  completed_count: number
}

export interface FeedUrl {
  token: string
  ics_path: string
}

export interface ProgramModifyPreview {
  program_id: number
  preview: ProgramPreview
  completed_preserved: number
  future_count: number
}

// ---- objectives / constraints --------------------------------------------- //
export interface Objective {
  id: number
  name: string
  kind: 'dated' | 'open_ended'
  target_date: string | null
  // Last day of a multi-day event (>= target_date); null = single-day event.
  event_end_date: string | null
  sport: string | null
  demands_profile: Record<string, unknown> | null
  is_primary: boolean
  // Rank among concurrent objectives (higher = more important; tiebreak on dates).
  priority: number
  // Parent objective this is a training milestone of (null = standalone peak).
  parent_objective_id: number | null
  created_at: string
  updated_at: string
}

export interface Constraint {
  id: number
  kind: 'injury' | 'schedule' | 'equipment'
  label: string
  directives: string | null
  defer_to_professional: boolean
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface ProgramStrategy {
  program_id: number
  name: string
  coach_summary: string | null
}

export interface ActiveObjective {
  // The derived *focus* objective (manual pin → next dated peak → standing goal).
  objective: Objective | null
  // All top-level objectives the user holds: dated peaks chronological, then
  // open-ended standing goals by priority. Sub-objectives are NOT here.
  objectives: Objective[]
  // The focus objective's training milestones (its sub-objectives), chronological.
  milestones: Objective[]
  constraints: Constraint[]
  active_program: ProgramStrategy | null
}

export interface ObjectiveInput {
  name: string
  kind?: 'dated' | 'open_ended'
  target_date?: string | null
  // Last day of a multi-day event (>= target_date); omit for a single-day event.
  event_end_date?: string | null
  sport?: string | null
  is_primary?: boolean
  // Rank among concurrent objectives (higher = more important).
  priority?: number
  // Set to nest under a parent (create a sub-objective); null/omit = standalone.
  parent_objective_id?: number | null
}

export interface ConstraintInput {
  kind: 'injury' | 'schedule' | 'equipment'
  label: string
  directives?: string | null
  defer_to_professional?: boolean | null
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
  startWorkout: (body: {
    template_id?: number | null
    name?: string | null
    tags?: string[]
    pre_workout_fuel?: string | null
  }) => req<WorkoutSession>('/workouts', { method: 'POST', body: JSON.stringify(body) }),
  listActivityTemplates: () => req<ActivityTemplate[]>('/workouts/activity-templates'),
  logActivity: (body: ActivityLogInput) =>
    req<WorkoutSession>('/workouts/activity', { method: 'POST', body: JSON.stringify(body) }),
  // route derivation — all three feed the same editable activity route fields
  searchTrails: (q: string) =>
    req<{ candidates: TrailCandidate[] }>(`/routes/search?q=${encodeURIComponent(q)}`),
  measureRoute: (points: RoutePoint[]) =>
    req<RouteStats>('/routes/measure', { method: 'POST', body: JSON.stringify({ points }) }),
  importGpx: (gpxText: string) =>
    req<RouteStats>('/routes/import-gpx', { method: 'POST', body: gpxText }),
  listWorkouts: () => req<WorkoutSummary[]>('/workouts'),
  getWorkout: (id: number) => req<WorkoutSession>(`/workouts/${id}`),
  updateWorkout: (id: number, body: WorkoutSessionUpdate) =>
    req<WorkoutSession>(`/workouts/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  // Materializes one virtual (expanded-on-read) occurrence of a recurring
  // activity into a real, linked row — idempotent (re-tapping an
  // already-materialized occurrence just returns it).
  materializeOccurrence: (id: number, occurrenceDate: string) =>
    req<WorkoutSession>(`/workouts/${id}/occurrences`, {
      method: 'POST',
      body: JSON.stringify({ occurrence_date: occurrenceDate }),
    }),
  // Optionally records the end-of-workout 1–10 energy/intensity self-report;
  // omit the body to just close the session out.
  finishWorkout: (id: number, body?: { energy_level?: number; workout_intensity?: number }) =>
    req<WorkoutSession>(`/workouts/${id}/finish`, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    }),
  deleteWorkout: (id: number) => req<void>(`/workouts/${id}`, { method: 'DELETE' }),
  addWorkoutExercise: (sessionId: number, body: TemplateExerciseInput) =>
    req<SessionExercise>(`/workouts/${sessionId}/exercises`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateWorkoutExercise: (
    sessionId: number,
    seId: number,
    body: Partial<{
      target_sets: number | null
      target_reps: number | null
      target_weight: number | null
      target_duration_seconds: number | null
      rest_seconds: number | null
      notes: string | null
      order_index: number
    }>,
  ) =>
    req<SessionExercise>(`/workouts/${sessionId}/exercises/${seId}`, {
      method: 'PATCH',
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
      done?: boolean
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
  // Mechanically slides missed workouts onto the next fit-to-train-on day —
  // no LLM, no confirmation, safe to call unconditionally on every Plan-page
  // mount (idempotent: a no-op once nothing is missed).
  rescheduleMissed: () => req<PlannedWorkout[]>('/plan/reschedule-missed', { method: 'POST' }),
  listPrograms: () => req<ProgramSummary[]>('/plan/programs'),
  deleteProgram: (id: number) => req<void>(`/plan/programs/${id}`, { method: 'DELETE' }),
  feedUrl: () => req<FeedUrl>('/plan/feed-url'),
  rotateFeedUrl: () => req<FeedUrl>('/plan/feed-url/rotate', { method: 'POST' }),

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
  coachModifyProgram: (programId: number, message: string) =>
    req<ProgramModifyPreview>(`/coach/programs/${programId}/modify`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),
  coachApplyProgram: (programId: number, spec: ProgramSpec, name?: string) =>
    req<{ id: number; name: string }>(`/coach/programs/${programId}`, {
      method: 'PUT',
      body: JSON.stringify({ spec, name: name ?? null }),
    }),
  // Speech-to-text: POST the raw audio blob (not JSON), get back transcribed text.
  transcribe: async (blob: Blob): Promise<string> => {
    const res = await fetch(`${BASE}/coach/transcribe`, {
      method: 'POST',
      headers: { 'Content-Type': blob.type || 'audio/webm' },
      body: blob,
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
    return ((await res.json()).text as string) ?? ''
  },

  // objectives / constraints
  activeObjective: () => req<ActiveObjective>('/objectives/active'),
  listObjectives: () => req<Objective[]>('/objectives'),
  createObjective: (body: ObjectiveInput) =>
    req<Objective>('/objectives', { method: 'POST', body: JSON.stringify(body) }),
  updateObjective: (id: number, body: Partial<ObjectiveInput>) =>
    req<Objective>(`/objectives/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteObjective: (id: number) => req<void>(`/objectives/${id}`, { method: 'DELETE' }),
  listConstraints: () => req<Constraint[]>('/constraints'),
  createConstraint: (body: ConstraintInput) =>
    req<Constraint>('/constraints', { method: 'POST', body: JSON.stringify(body) }),
  updateConstraint: (id: number, body: Partial<ConstraintInput & { is_active: boolean }>) =>
    req<Constraint>(`/constraints/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteConstraint: (id: number) => req<void>(`/constraints/${id}`, { method: 'DELETE' }),

  // web push
  pushPublicKey: () => req<{ key: string }>('/push/public-key'),
  pushSubscribe: (sub: { endpoint: string; keys: { p256dh: string; auth: string } }) =>
    req<void>('/push/subscribe', { method: 'POST', body: JSON.stringify(sub) }),
  pushUnsubscribe: (endpoint: string) =>
    req<void>('/push/unsubscribe', { method: 'POST', body: JSON.stringify({ endpoint }) }),
  pushSchedule: (timerId: string, delaySeconds: number, title: string, body = '') =>
    req<void>('/push/schedule', {
      method: 'POST',
      body: JSON.stringify({ timer_id: timerId, delay_seconds: delaySeconds, title, body }),
    }),
  pushCancel: (timerId: string) =>
    req<void>('/push/cancel', { method: 'POST', body: JSON.stringify({ timer_id: timerId }) }),
}
