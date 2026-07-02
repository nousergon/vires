import { type FocusEvent, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type SessionExercise, type SetEntry, type WorkoutSession } from '../lib/api'
import { useCountdown, fmtClock, fireTimerAlert } from '../lib/timer'
import { useWakeLock } from '../lib/wakeLock'
import { schedulePush, cancelPush } from '../lib/push'
import { useSettings } from '../lib/useSettings'
import { Button, Card, EmptyState, PageTitle, Spinner } from '../components/ui'
import ExercisePicker from '../components/ExercisePicker'
import PlateCalculatorSheet from '../components/PlateCalculatorSheet'
import ActivityForm from '../components/ActivityForm'

export const ACTIVE_KEY = 'vires.activeWorkout'

// A boolean preference remembered per session exercise in localStorage (so a
// choice on one move doesn't affect the others). `null` storage falls back to
// the provided default; "0" means explicitly off.
function useFlag(key: string, dflt: boolean): [boolean, (v: boolean) => void] {
  const [on, setOn] = useState(() => {
    const raw = localStorage.getItem(key)
    return raw == null ? dflt : raw !== '0'
  })
  const set = (v: boolean) => {
    localStorage.setItem(key, v ? '1' : '0')
    setOn(v)
  }
  return [on, set]
}

// Which input columns a set row shows. Independent per exercise; defaults derive
// from whether the exercise is timed (a hold) — a timed move starts as
// timer-only, a normal move as weight + reps — but each can be toggled freely so
// e.g. a weighted plank can show weight + timer.
interface Cols {
  weight: boolean
  reps: boolean
  timer: boolean
}

// CSS grid track template shared by an exercise's header row and its set rows so
// the two always line up. Built from the enabled columns: Set# · [weight] ·
// [reps] · [hold-secs ▶] · ✓ · ✕.
function gridTemplate(cols: Cols): string {
  const tracks = ['2rem']
  if (cols.weight) tracks.push('minmax(0,1fr)')
  if (cols.reps) tracks.push('minmax(0,1fr)')
  if (cols.timer) tracks.push('minmax(0,1fr)', '2rem')
  tracks.push('2rem', '1.5rem')
  return tracks.join(' ')
}

// Select-all on focus so tapping a number field overwrites the value instead of
// forcing the user to clear it first.
const selectOnFocus = (e: FocusEvent<HTMLInputElement>) => e.currentTarget.select()

function useActiveId(): [number | null, (id: number | null) => void] {
  const [id, setId] = useState<number | null>(() => {
    const raw = localStorage.getItem(ACTIVE_KEY)
    return raw ? Number(raw) : null
  })
  const set = (v: number | null) => {
    if (v == null) localStorage.removeItem(ACTIVE_KEY)
    else localStorage.setItem(ACTIVE_KEY, String(v))
    setId(v)
  }
  return [id, set]
}

export default function WorkoutPage() {
  const [activeId, setActiveId] = useActiveId()
  return activeId == null ? (
    <StartView onStarted={setActiveId} />
  ) : (
    <ActiveWorkout id={activeId} onClear={() => setActiveId(null)} />
  )
}

// --------------------------------------------------------------------------- //
function StartView({ onStarted }: { onStarted: (id: number) => void }) {
  const { data: templates = [], isLoading } = useQuery({
    queryKey: ['templates'],
    queryFn: api.listTemplates,
  })
  const start = useMutation({
    mutationFn: (templateId: number | null) => api.startWorkout({ template_id: templateId }),
    onSuccess: (ws) => onStarted(ws.id),
  })
  const [activityOpen, setActivityOpen] = useState(false)

  return (
    <div>
      <PageTitle>Train</PageTitle>
      <Button className="w-full" onClick={() => start.mutate(null)} disabled={start.isPending}>
        Start empty workout
      </Button>
      <Button variant="secondary" className="mt-2 w-full" onClick={() => setActivityOpen(true)}>
        🏃 Log an activity
      </Button>
      <ActivityForm open={activityOpen} onClose={() => setActivityOpen(false)} />

      <h2 className="mb-2 mt-6 text-sm font-semibold uppercase tracking-wide text-slate-400">
        Start from a routine
      </h2>
      {isLoading ? (
        <Spinner />
      ) : templates.length === 0 ? (
        <EmptyState title="No routines yet" hint="Build one in the Routines tab." />
      ) : (
        <div className="space-y-2">
          {templates.map((t) => (
            <Card key={t.id} className="flex items-center justify-between">
              <div>
                <div className="font-semibold text-slate-100">{t.name}</div>
                <div className="text-xs text-slate-400">{t.exercise_count} exercises</div>
              </div>
              <Button variant="secondary" onClick={() => start.mutate(t.id)} disabled={start.isPending}>
                Start
              </Button>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

// --------------------------------------------------------------------------- //
type TimerKind = 'rest' | 'hold'
// (kind, seId, setId, secs, onFinish) — setId anchors the inline bar to the set
// that started the timer so it renders directly beneath that row.
type RunTimer = (kind: TimerKind, seId: number, setId: number, secs: number, onFinish?: () => void) => void
type TimerCtx = { seId: number; setId: number; kind: TimerKind }

function ActiveWorkout({ id, onClear }: { id: number; onClear: () => void }) {
  const qc = useQueryClient()
  const nav = useNavigate()
  const settings = useSettings()
  const timer = useCountdown((label) => fireTimerAlert(settings, label))
  const [timerCtx, setTimerCtx] = useState<TimerCtx | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)

  // Keep the screen awake while a timer runs so the end alert reliably fires.
  useWakeLock(timer.running && settings.timer_keep_awake)

  // The running timer (for the locked-screen push fallback). When the app is
  // backgrounded mid-timer we schedule a server push for the remaining time; on
  // return to the foreground (or when the timer ends/stops) we cancel it, so the
  // push only ever fires when the in-app beep can't.
  const activeTimer = useRef<{ id: string; endAt: number; title: string } | null>(null)

  useEffect(() => {
    function onVisibility() {
      const at = activeTimer.current
      if (!at) return
      if (document.visibilityState === 'hidden') {
        if (settings.timer_notification) {
          const remaining = (at.endAt - Date.now()) / 1000
          if (remaining > 0) schedulePush(at.id, remaining, at.title)
        }
      } else {
        cancelPush(at.id)
      }
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => document.removeEventListener('visibilitychange', onVisibility)
  }, [settings.timer_notification])

  const { data: ws, isLoading, error, refetch, isRefetching } = useQuery({
    queryKey: ['workout', id],
    queryFn: () => api.getWorkout(id),
    // A 404 means the active-workout pointer is stale (the session was deleted) —
    // don't retry it; self-heal below. Other errors (transient) still retry.
    retry: (count, err) => !String((err as Error).message).startsWith('404') && count < 2,
  })
  // Recover from a deleted/missing active session: clear the stale pointer so the
  // Train page falls back to the start view instead of spinning forever.
  const missing = !!error && String((error as Error).message).startsWith('404')
  useEffect(() => {
    if (missing) onClear()
  }, [missing, onClear])
  const invalidate = () => qc.invalidateQueries({ queryKey: ['workout', id] })

  function clearActiveTimer() {
    const at = activeTimer.current
    if (at) cancelPush(at.id)
    activeTimer.current = null
  }

  const runTimer: RunTimer = (kind, seId, setId, secs, onFinish) => {
    setTimerCtx({ seId, setId, kind })
    const title = kind === 'hold' ? 'Hold complete' : 'Rest over'
    activeTimer.current = {
      id: `${id}-${seId}-${Date.now()}`,
      endAt: Date.now() + secs * 1000,
      title,
    }
    timer.start(
      secs,
      () => {
        clearActiveTimer()
        setTimerCtx(null)
        onFinish?.()
      },
      title,
    )
  }
  const stopTimer = () => {
    clearActiveTimer()
    timer.stop()
    setTimerCtx(null)
  }

  const addExercise = useMutation({
    mutationFn: (exerciseId: number) => api.addWorkoutExercise(id, { exercise_id: exerciseId }),
    onSuccess: invalidate,
  })
  // Reorder: swap an exercise's order_index with its neighbour, then refetch.
  const move = useMutation({
    mutationFn: async ({ idx, dir }: { idx: number; dir: -1 | 1 }) => {
      const list = ws!.exercises
      const a = list[idx]
      const b = list[idx + dir]
      if (!a || !b) return
      await Promise.all([
        api.updateWorkoutExercise(id, a.id, { order_index: b.order_index }),
        api.updateWorkoutExercise(id, b.id, { order_index: a.order_index }),
      ])
    },
    onSuccess: invalidate,
  })
  const finish = useMutation({
    mutationFn: () => api.finishWorkout(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['workouts'] })
      onClear()
      nav('/history')
    },
  })
  const discard = useMutation({
    mutationFn: () => api.deleteWorkout(id),
    onSuccess: () => onClear(),
  })

  if (missing) return null // stale pointer cleared; parent switches to the start view
  if (isLoading) return <Spinner />
  // A settled non-404 error (network blip, 500, etc.) leaves `ws` permanently
  // undefined with no automatic retry — surface an explicit error state with an
  // escape hatch instead of spinning forever (the "wheel of death" bug).
  if (error || !ws) {
    return (
      <div className="space-y-3">
        <EmptyState
          title="Couldn't load this workout"
          hint="Check your connection, then retry — or clear it and start fresh."
        />
        <Button className="w-full" onClick={() => refetch()} disabled={isRefetching}>
          Retry
        </Button>
        <button className="w-full py-2 text-sm text-red-400" onClick={onClear}>
          Clear active workout
        </button>
      </div>
    )
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">{ws.name || 'Workout'}</h1>
          <Elapsed start={ws.started_at} />
        </div>
        <Button onClick={() => finish.mutate()} disabled={finish.isPending}>
          Finish
        </Button>
      </div>

      <div className="space-y-4">
        {ws.exercises.map((se, i) => (
          <ExerciseBlock
            key={se.id}
            session={ws}
            se={se}
            timer={timer}
            timerCtx={timerCtx}
            runTimer={runTimer}
            stopTimer={stopTimer}
            onChanged={invalidate}
            canMoveUp={i > 0}
            canMoveDown={i < ws.exercises.length - 1}
            onMoveUp={() => move.mutate({ idx: i, dir: -1 })}
            onMoveDown={() => move.mutate({ idx: i, dir: 1 })}
          />
        ))}
      </div>

      <Button variant="secondary" className="mt-4 w-full" onClick={() => setPickerOpen(true)}>
        + Add exercise
      </Button>

      <button
        className="mt-6 w-full py-2 text-sm text-red-400"
        onClick={() => {
          if (confirm('Discard this workout?')) discard.mutate()
        }}
      >
        Discard workout
      </button>

      <ExercisePicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onSelect={(ex) => addExercise.mutate(ex.id)}
      />
    </div>
  )
}

function Elapsed({ start }: { start: string }) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])
  const secs = Math.max(0, Math.floor((now - new Date(start).getTime()) / 1000))
  return <div className="text-sm text-slate-400">{fmtClock(secs)} elapsed</div>
}

// Small segmented toggle for a set-row column (weight / reps / timer).
function ColToggle({ label, on, onToggle }: { label: string; on: boolean; onToggle: (v: boolean) => void }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={() => onToggle(!on)}
      className={`rounded-full border px-2.5 py-0.5 text-xs ${
        on
          ? 'border-amber-600/60 bg-amber-900/30 text-amber-200'
          : 'border-slate-700 text-slate-500'
      }`}
    >
      {label}
    </button>
  )
}

// Inline countdown shown directly under the set it belongs to. The seconds field
// re-bases the running timer on the fly; ±30s nudges it.
function InlineTimerBar({
  timer,
  kind,
  onAdd,
  onSub,
  onSkip,
}: {
  timer: ReturnType<typeof useCountdown>
  kind: TimerKind
  onAdd: () => void
  onSub: () => void
  onSkip: () => void
}) {
  const pct = timer.total > 0 ? (timer.remaining / timer.total) * 100 : 0
  const hold = kind === 'hold'
  const accent = hold ? 'text-sky-300' : 'text-amber-300'
  const bar = hold ? 'bg-sky-500' : 'bg-amber-500'
  const border = hold ? 'border-sky-700/50 bg-sky-900/20' : 'border-amber-700/50 bg-amber-900/20'
  // Seeded once when the bar mounts (i.e. when the timer starts); editing it
  // commits a new total via setDuration.
  const [secs, setSecs] = useState(String(timer.total))
  const commit = () => {
    const n = secs === '' ? 0 : Number(secs)
    if (n > 0) timer.setDuration(n)
  }
  return (
    <div className={`mt-2 rounded-lg border px-3 py-2 ${border}`}>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="text-xs font-semibold uppercase text-slate-400">
          {hold ? 'Hold' : 'Rest'}
        </span>
        <span className={`font-mono text-lg font-bold ${accent}`}>{fmtClock(timer.remaining)}</span>
        <div className="flex items-center gap-1">
          <input
            type="number"
            inputMode="numeric"
            aria-label="Set timer seconds"
            value={secs}
            onFocus={selectOnFocus}
            onChange={(e) => setSecs(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === 'Enter') e.currentTarget.blur()
            }}
            className="w-12 rounded bg-slate-800 px-1 py-0.5 text-center text-xs outline-none focus:ring-1 focus:ring-amber-500"
          />
          <span className="text-xs text-slate-500">s</span>
          <button className="rounded px-2 py-0.5 text-xs text-slate-300" onClick={onSub}>
            −30s
          </button>
          <button className="rounded px-2 py-0.5 text-xs text-slate-300" onClick={onAdd}>
            +30s
          </button>
          <button className="rounded px-2 py-0.5 text-xs text-slate-300" onClick={onSkip}>
            {hold ? 'Stop' : 'Skip'}
          </button>
        </div>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-700">
        <div className={`h-full ${bar} transition-[width] duration-300`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

// --------------------------------------------------------------------------- //
function ExerciseBlock({
  session,
  se,
  timer,
  timerCtx,
  runTimer,
  stopTimer,
  onChanged,
  canMoveUp,
  canMoveDown,
  onMoveUp,
  onMoveDown,
}: {
  session: WorkoutSession
  se: SessionExercise
  timer: ReturnType<typeof useCountdown>
  timerCtx: TimerCtx | null
  runTimer: RunTimer
  stopTimer: () => void
  onChanged: () => void
  canMoveUp: boolean
  canMoveDown: boolean
  onMoveUp: () => void
  onMoveDown: () => void
}) {
  const settings = useSettings()
  const prev = se.previous_performance
  const timed = se.exercise.is_timed
  // Independent per-exercise column toggles; a normal move defaults to
  // weight + reps, a timed move to timer-only, but any combination is allowed.
  const [showWeight, setShowWeight] = useFlag(`vires.col.weight.${se.id}`, !timed)
  const [showReps, setShowReps] = useFlag(`vires.col.reps.${se.id}`, !timed)
  const [showTimer, setShowTimer] = useFlag(`vires.col.timer.${se.id}`, timed)
  const cols: Cols = { weight: showWeight, reps: showReps, timer: showTimer }
  const template = gridTemplate(cols)

  const [restEnabled, setRestEnabled] = useFlag(`vires.restOn.${se.id}`, true)
  const restSecs = se.rest_seconds ?? settings.default_rest_seconds
  const [restInput, setRestInput] = useState(String(restSecs))
  const holdSecs = se.target_duration_seconds ?? 60

  const [plateCalcOpen, setPlateCalcOpen] = useState(false)
  const lastSetWeight = se.sets[se.sets.length - 1]?.weight
  const plateCalcSeed = lastSetWeight ?? se.target_weight ?? prev?.sets[0]?.weight ?? null

  async function addSet() {
    const idx = se.sets.length
    const ghost = prev?.sets[idx] ?? prev?.sets[prev.sets.length - 1]
    const body: {
      reps?: number | null
      weight?: number | null
      duration_seconds?: number | null
      done: boolean
    } = { done: false }
    // Hidden weight logs as 0 (bodyweight). Seed visible columns from the prior
    // session / routine targets so a new row is a sensible editable target.
    body.weight = showWeight ? (ghost?.weight ?? se.target_weight ?? null) : 0
    if (showReps) body.reps = ghost?.reps ?? se.target_reps ?? null
    if (showTimer) body.duration_seconds = holdSecs
    await api.logSet(session.id, se.id, body)
    onChanged()
  }

  async function saveRest() {
    const secs = restInput === '' ? settings.default_rest_seconds : Number(restInput)
    if (secs !== restSecs) {
      await api.updateWorkoutExercise(session.id, se.id, { rest_seconds: secs })
      onChanged()
    }
  }

  return (
    <Card>
      <div className="mb-1 flex items-center justify-between">
        <h3 className="font-semibold text-slate-100">{se.exercise.name}</h3>
        <div className="flex items-center gap-2">
          <button
            className="px-1 text-slate-500 disabled:opacity-25"
            disabled={!canMoveUp}
            onClick={onMoveUp}
            title="Move up"
          >
            ↑
          </button>
          <button
            className="px-1 text-slate-500 disabled:opacity-25"
            disabled={!canMoveDown}
            onClick={onMoveDown}
            title="Move down"
          >
            ↓
          </button>
          <button
            className="text-xs text-slate-500"
            onClick={async () => {
              await api.removeWorkoutExercise(session.id, se.id)
              onChanged()
            }}
          >
            remove
          </button>
        </div>
      </div>

      <PrevHint prev={prev} unit={settings.weight_unit} />

      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        <ColToggle label="Weight" on={showWeight} onToggle={setShowWeight} />
        <ColToggle label="Reps" on={showReps} onToggle={setShowReps} />
        <ColToggle label="Timer" on={showTimer} onToggle={setShowTimer} />
        {showWeight && (
          <button
            className="rounded-full bg-slate-800 px-2.5 py-1 text-xs text-slate-300"
            onClick={() => setPlateCalcOpen(true)}
            title="Plate calculator"
          >
            🏋 Plates
          </button>
        )}
      </div>
      <PlateCalculatorSheet
        open={plateCalcOpen}
        onClose={() => setPlateCalcOpen(false)}
        unit={settings.weight_unit}
        initialWeight={plateCalcSeed}
      />

      <label className="mt-1.5 flex items-center gap-2 text-xs text-slate-400">
        <input
          type="checkbox"
          checked={restEnabled}
          onChange={(e) => setRestEnabled(e.target.checked)}
          className="h-3.5 w-3.5 accent-amber-500"
        />
        Rest timer
        <input
          type="number"
          inputMode="numeric"
          value={restInput}
          disabled={!restEnabled}
          onFocus={selectOnFocus}
          onChange={(e) => setRestInput(e.target.value)}
          onBlur={saveRest}
          className="w-14 rounded bg-slate-800 px-1.5 py-0.5 text-center outline-none focus:ring-1 focus:ring-amber-500 disabled:opacity-40"
        />
        <span>s</span>
      </label>

      <div className="mt-2 space-y-1.5">
        <div
          className="grid gap-2 px-1 text-xs uppercase text-slate-500"
          style={{ gridTemplateColumns: template }}
        >
          <span>Set</span>
          {showWeight && <span>{settings.weight_unit}</span>}
          {showReps && <span>Reps</span>}
          {showTimer && (
            <>
              <span>Hold (s)</span>
              <span className="text-center">▶</span>
            </>
          )}
          <span className="text-center">✓</span>
          <span />
        </div>
        {se.sets.map((s) => (
          <div key={s.id}>
            <SetRow
              sessionId={session.id}
              seId={se.id}
              set={s}
              cols={cols}
              template={template}
              holdDefault={holdSecs}
              restSecs={restSecs}
              restEnabled={restEnabled}
              runTimer={runTimer}
              onChanged={onChanged}
            />
            {timerCtx?.seId === se.id && timerCtx.setId === s.id && (
              <InlineTimerBar
                timer={timer}
                kind={timerCtx.kind}
                onAdd={() => timer.addSeconds(30)}
                onSub={() => timer.addSeconds(-30)}
                onSkip={stopTimer}
              />
            )}
          </div>
        ))}
      </div>

      <button
        onClick={addSet}
        className="mt-2 w-full rounded-lg border border-slate-700 py-2 text-sm text-slate-300 hover:bg-slate-800"
      >
        + Add set
      </button>
    </Card>
  )
}

function PrevHint({
  prev,
  unit,
}: {
  prev: SessionExercise['previous_performance']
  unit: string
}) {
  if (!prev || prev.sets.length === 0) return null
  const summary = prev.sets
    .filter((s) => !s.is_warmup)
    .map((s) => `${s.weight ?? '—'}${unit}×${s.reps ?? '—'}`)
    .join(', ')
  return (
    <p className="text-xs text-slate-400">
      Last time ({new Date(prev.date).toLocaleDateString()}): {summary || '—'}
    </p>
  )
}

function SetNumButton({
  sessionId,
  seId,
  set,
  onChanged,
}: {
  sessionId: number
  seId: number
  set: SetEntry
  onChanged: () => void
}) {
  return (
    <button
      onClick={async () => {
        await api.updateSet(sessionId, seId, set.id, { is_warmup: !set.is_warmup })
        onChanged()
      }}
      className={`h-7 w-7 rounded-md text-xs font-bold ${
        set.is_warmup ? 'bg-amber-600/40 text-amber-200' : 'bg-slate-700 text-slate-300'
      }`}
      title="Toggle warm-up"
    >
      {set.is_warmup ? 'W' : set.set_number}
    </button>
  )
}

function DeleteSetButton({
  sessionId,
  seId,
  setId,
  onChanged,
}: {
  sessionId: number
  seId: number
  setId: number
  onChanged: () => void
}) {
  return (
    <button
      className="text-slate-600 hover:text-red-400"
      onClick={async () => {
        await api.deleteSet(sessionId, seId, setId)
        onChanged()
      }}
    >
      ✕
    </button>
  )
}

// A single set row whose visible inputs follow the exercise's column toggles:
// optional weight, optional reps, and an optional hold timer (a duration field
// plus a ▶ that counts the hold down, logs it, then auto-starts rest). ✓ marks
// the set done and — when the rest timer is enabled — kicks off the rest bar.
function SetRow({
  sessionId,
  seId,
  set,
  cols,
  template,
  holdDefault,
  restSecs,
  restEnabled,
  runTimer,
  onChanged,
}: {
  sessionId: number
  seId: number
  set: SetEntry
  cols: Cols
  template: string
  holdDefault: number
  restSecs: number
  restEnabled: boolean
  runTimer: RunTimer
  onChanged: () => void
}) {
  const [weight, setWeight] = useState(set.weight?.toString() ?? '')
  const [reps, setReps] = useState(set.reps?.toString() ?? '')
  const [dur, setDur] = useState((set.duration_seconds ?? holdDefault).toString())
  const done = !!set.completed_at
  const seconds = () => (dur === '' ? holdDefault : Number(dur))

  const save = (patch: { weight?: number; reps?: number; duration_seconds?: number }) =>
    api.updateSet(sessionId, seId, set.id, patch)

  // Persist whichever toggled-on fields the row carries, mark the set done, and
  // start the rest countdown beneath this row.
  async function markDone(nowDone: boolean) {
    const patch: {
      done: boolean
      weight?: number
      reps?: number
      duration_seconds?: number
    } = { done: nowDone }
    if (cols.weight) patch.weight = weight === '' ? undefined : Number(weight)
    if (cols.reps) patch.reps = reps === '' ? undefined : Number(reps)
    if (cols.timer) patch.duration_seconds = seconds()
    await api.updateSet(sessionId, seId, set.id, patch)
    if (nowDone && restEnabled) runTimer('rest', seId, set.id, restSecs)
    onChanged()
  }

  // ▶ : count the hold down, then log it done and roll into rest.
  function startHold() {
    runTimer('hold', seId, set.id, seconds(), () => {
      markDone(true)
    })
  }

  const cell = `w-full min-w-0 rounded-lg px-2 py-2 text-center outline-none focus:ring-1 focus:ring-amber-500 ${
    done ? 'bg-emerald-900/30 text-slate-300' : 'bg-slate-800'
  }`

  return (
    <div
      className={`grid items-center gap-2 rounded-lg ${done ? 'bg-emerald-900/10' : ''}`}
      style={{ gridTemplateColumns: template }}
    >
      <SetNumButton sessionId={sessionId} seId={seId} set={set} onChanged={onChanged} />
      {cols.weight && (
        <input
          type="number"
          inputMode="decimal"
          value={weight}
          onFocus={selectOnFocus}
          onChange={(e) => setWeight(e.target.value)}
          onBlur={() => save({ weight: weight === '' ? undefined : Number(weight) })}
          className={cell}
        />
      )}
      {cols.reps && (
        <input
          type="number"
          inputMode="numeric"
          value={reps}
          onFocus={selectOnFocus}
          onChange={(e) => setReps(e.target.value)}
          onBlur={() => save({ reps: reps === '' ? undefined : Number(reps) })}
          className={cell}
        />
      )}
      {cols.timer && (
        <>
          <input
            type="number"
            inputMode="numeric"
            value={dur}
            onFocus={selectOnFocus}
            onChange={(e) => setDur(e.target.value)}
            onBlur={() => save({ duration_seconds: seconds() })}
            className={cell}
          />
          <button
            onClick={startHold}
            title="Start hold"
            className="h-7 w-7 rounded-md bg-sky-600 text-sm font-bold text-slate-950"
          >
            ▶
          </button>
        </>
      )}
      <button
        onClick={() => markDone(!done)}
        title="Mark done"
        className={`h-7 w-7 rounded-md text-sm font-bold ${
          done ? 'bg-emerald-500 text-slate-950' : 'bg-slate-700 text-slate-400'
        }`}
      >
        ✓
      </button>
      <DeleteSetButton sessionId={sessionId} seId={seId} setId={set.id} onChanged={onChanged} />
    </div>
  )
}
