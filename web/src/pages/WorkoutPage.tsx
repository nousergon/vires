import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type SessionExercise, type SetEntry, type WorkoutSession } from '../lib/api'
import { useCountdown, fmtClock, fireTimerAlert } from '../lib/timer'
import { useWakeLock } from '../lib/wakeLock'
import { schedulePush, cancelPush } from '../lib/push'
import { useSettings } from '../lib/useSettings'
import { Button, Card, EmptyState, PageTitle, Spinner } from '../components/ui'
import ExercisePicker from '../components/ExercisePicker'

export const ACTIVE_KEY = 'vires.activeWorkout'

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

  return (
    <div>
      <PageTitle>Train</PageTitle>
      <Button className="w-full" onClick={() => start.mutate(null)} disabled={start.isPending}>
        Start empty workout
      </Button>

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
type RunTimer = (kind: TimerKind, seId: number, secs: number, onFinish?: () => void) => void

function ActiveWorkout({ id, onClear }: { id: number; onClear: () => void }) {
  const qc = useQueryClient()
  const nav = useNavigate()
  const settings = useSettings()
  const timer = useCountdown((label) => fireTimerAlert(settings, label))
  const [timerCtx, setTimerCtx] = useState<{ seId: number; kind: TimerKind } | null>(null)
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

  const { data: ws, isLoading, error } = useQuery({
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

  const runTimer: RunTimer = (kind, seId, secs, onFinish) => {
    setTimerCtx({ seId, kind })
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
  if (isLoading || !ws) return <Spinner />

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
        {ws.exercises.map((se) => (
          <ExerciseBlock
            key={se.id}
            session={ws}
            se={se}
            timer={timer}
            timerCtx={timerCtx}
            runTimer={runTimer}
            stopTimer={stopTimer}
            onChanged={invalidate}
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

// Inline countdown shown directly under the exercise it belongs to.
function InlineTimerBar({
  timer,
  kind,
  onAdd,
  onSkip,
}: {
  timer: ReturnType<typeof useCountdown>
  kind: TimerKind
  onAdd: () => void
  onSkip: () => void
}) {
  const pct = timer.total > 0 ? (timer.remaining / timer.total) * 100 : 0
  const hold = kind === 'hold'
  const accent = hold ? 'text-sky-300' : 'text-amber-300'
  const bar = hold ? 'bg-sky-500' : 'bg-amber-500'
  const border = hold ? 'border-sky-700/50 bg-sky-900/20' : 'border-amber-700/50 bg-amber-900/20'
  return (
    <div className={`mt-2 rounded-lg border px-3 py-2 ${border}`}>
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-xs font-semibold uppercase text-slate-400">
          {hold ? 'Hold' : 'Rest'}
        </span>
        <span className={`font-mono text-lg font-bold ${accent}`}>{fmtClock(timer.remaining)}</span>
        <div className="flex gap-1">
          {!hold && (
            <button className="rounded px-2 py-0.5 text-xs text-slate-300" onClick={onAdd}>
              +30s
            </button>
          )}
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
}: {
  session: WorkoutSession
  se: SessionExercise
  timer: ReturnType<typeof useCountdown>
  timerCtx: { seId: number; kind: TimerKind } | null
  runTimer: RunTimer
  stopTimer: () => void
  onChanged: () => void
}) {
  const settings = useSettings()
  const prev = se.previous_performance
  const restSecs = se.rest_seconds ?? settings.default_rest_seconds
  const timed = se.exercise.is_timed
  const holdSecs = se.target_duration_seconds ?? 60

  async function addSet() {
    const idx = se.sets.length
    const ghost = prev?.sets[idx] ?? prev?.sets[prev.sets.length - 1]
    if (timed) {
      await api.logSet(session.id, se.id, { duration_seconds: holdSecs })
    } else {
      await api.logSet(session.id, se.id, {
        reps: ghost?.reps ?? se.target_reps ?? null,
        weight: ghost?.weight ?? se.target_weight ?? null,
      })
    }
    onChanged()
  }

  const showBar = timerCtx?.seId === se.id

  return (
    <Card>
      <div className="mb-1 flex items-center justify-between">
        <h3 className="font-semibold text-slate-100">{se.exercise.name}</h3>
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

      <PrevHint prev={prev} unit={settings.weight_unit} />

      <div className="mt-2 space-y-1.5">
        {timed ? (
          <div className="grid grid-cols-[2rem_1fr_2rem_2rem_1.5rem] gap-2 px-1 text-xs uppercase text-slate-500">
            <span>Set</span>
            <span>Hold (s)</span>
            <span className="text-center">▶</span>
            <span className="text-center">✓</span>
            <span />
          </div>
        ) : (
          <div className="grid grid-cols-[2rem_1fr_1fr_2rem_1.5rem] gap-2 px-1 text-xs uppercase text-slate-500">
            <span>Set</span>
            <span>{settings.weight_unit}</span>
            <span>Reps</span>
            <span className="text-center">✓</span>
            <span />
          </div>
        )}
        {se.sets.map((s) =>
          timed ? (
            <TimedSetRow
              key={s.id}
              sessionId={session.id}
              seId={se.id}
              set={s}
              holdDefault={holdSecs}
              restSecs={restSecs}
              runTimer={runTimer}
              onChanged={onChanged}
            />
          ) : (
            <SetRow
              key={s.id}
              sessionId={session.id}
              seId={se.id}
              set={s}
              restSecs={restSecs}
              runTimer={runTimer}
              onChanged={onChanged}
            />
          ),
        )}
      </div>

      {showBar && (
        <InlineTimerBar
          timer={timer}
          kind={timerCtx.kind}
          onAdd={() => timer.addSeconds(30)}
          onSkip={stopTimer}
        />
      )}

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

function SetRow({
  sessionId,
  seId,
  set,
  restSecs,
  runTimer,
  onChanged,
}: {
  sessionId: number
  seId: number
  set: SetEntry
  restSecs: number
  runTimer: RunTimer
  onChanged: () => void
}) {
  const [weight, setWeight] = useState(set.weight?.toString() ?? '')
  const [reps, setReps] = useState(set.reps?.toString() ?? '')
  const done = !!set.completed_at

  const save = (patch: { weight?: number; reps?: number }) =>
    api.updateSet(sessionId, seId, set.id, patch)

  async function toggleDone() {
    const nowDone = !done
    await api.updateSet(sessionId, seId, set.id, {
      done: nowDone,
      weight: weight === '' ? undefined : Number(weight),
      reps: reps === '' ? undefined : Number(reps),
    })
    if (nowDone) runTimer('rest', seId, restSecs)
    onChanged()
  }

  const cell = `rounded-lg px-3 py-2 text-center outline-none focus:ring-1 focus:ring-amber-500 ${
    done ? 'bg-emerald-900/30 text-slate-300' : 'bg-slate-800'
  }`

  return (
    <div
      className={`grid grid-cols-[2rem_1fr_1fr_2rem_1.5rem] items-center gap-2 rounded-lg ${
        done ? 'bg-emerald-900/10' : ''
      }`}
    >
      <SetNumButton sessionId={sessionId} seId={seId} set={set} onChanged={onChanged} />
      <input
        type="number"
        inputMode="decimal"
        value={weight}
        onChange={(e) => setWeight(e.target.value)}
        onBlur={() => save({ weight: weight === '' ? undefined : Number(weight) })}
        className={cell}
      />
      <input
        type="number"
        inputMode="numeric"
        value={reps}
        onChange={(e) => setReps(e.target.value)}
        onBlur={() => save({ reps: reps === '' ? undefined : Number(reps) })}
        className={cell}
      />
      <button
        onClick={toggleDone}
        title="Mark set done"
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

// Timed (isometric / hold) exercise row: a duration + a ▶ hold countdown that
// logs the hold and then auto-starts rest.
function TimedSetRow({
  sessionId,
  seId,
  set,
  holdDefault,
  restSecs,
  runTimer,
  onChanged,
}: {
  sessionId: number
  seId: number
  set: SetEntry
  holdDefault: number
  restSecs: number
  runTimer: RunTimer
  onChanged: () => void
}) {
  const [dur, setDur] = useState((set.duration_seconds ?? holdDefault).toString())
  const done = !!set.completed_at
  const seconds = () => (dur === '' ? holdDefault : Number(dur))

  async function complete() {
    await api.updateSet(sessionId, seId, set.id, { done: true, duration_seconds: seconds() })
    onChanged()
    runTimer('rest', seId, restSecs)
  }

  function startHold() {
    runTimer('hold', seId, seconds(), () => {
      complete()
    })
  }

  const cell = `rounded-lg px-3 py-2 text-center outline-none focus:ring-1 focus:ring-amber-500 ${
    done ? 'bg-emerald-900/30 text-slate-300' : 'bg-slate-800'
  }`

  return (
    <div
      className={`grid grid-cols-[2rem_1fr_2rem_2rem_1.5rem] items-center gap-2 rounded-lg ${
        done ? 'bg-emerald-900/10' : ''
      }`}
    >
      <SetNumButton sessionId={sessionId} seId={seId} set={set} onChanged={onChanged} />
      <input
        type="number"
        inputMode="numeric"
        value={dur}
        onChange={(e) => setDur(e.target.value)}
        onBlur={() => api.updateSet(sessionId, seId, set.id, { duration_seconds: seconds() })}
        className={cell}
      />
      <button
        onClick={startHold}
        title="Start hold"
        className="h-7 w-7 rounded-md bg-sky-600 text-sm font-bold text-slate-950"
      >
        ▶
      </button>
      <button
        onClick={complete}
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
