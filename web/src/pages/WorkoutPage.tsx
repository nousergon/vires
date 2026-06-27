import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type SessionExercise, type SetEntry, type WorkoutSession } from '../lib/api'
import { useCountdown, fmtClock } from '../lib/timer'
import { useSettings } from '../lib/useSettings'
import { Button, Card, EmptyState, PageTitle, Spinner } from '../components/ui'
import ExercisePicker from '../components/ExercisePicker'

const ACTIVE_KEY = 'vires.activeWorkout'

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
function ActiveWorkout({ id, onClear }: { id: number; onClear: () => void }) {
  const qc = useQueryClient()
  const nav = useNavigate()
  const rest = useCountdown()
  const [pickerOpen, setPickerOpen] = useState(false)

  const { data: ws, isLoading } = useQuery({
    queryKey: ['workout', id],
    queryFn: () => api.getWorkout(id),
  })
  const invalidate = () => qc.invalidateQueries({ queryKey: ['workout', id] })

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
    onSuccess: () => {
      onClear()
    },
  })

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

      {rest.running && (
        <div className="sticky top-0 z-10 mb-3 flex items-center justify-between rounded-xl border border-amber-700/50 bg-amber-900/30 px-4 py-2">
          <span className="font-mono text-xl font-bold text-amber-300">{fmtClock(rest.remaining)}</span>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => rest.addSeconds(30)}>
              +30s
            </Button>
            <Button variant="ghost" onClick={rest.stop}>
              Skip
            </Button>
          </div>
        </div>
      )}

      <div className="space-y-4">
        {ws.exercises.map((se) => (
          <ExerciseBlock
            key={se.id}
            session={ws}
            se={se}
            onChanged={invalidate}
            onRest={(secs) => rest.start(secs)}
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

// --------------------------------------------------------------------------- //
function ExerciseBlock({
  session,
  se,
  onChanged,
  onRest,
}: {
  session: WorkoutSession
  se: SessionExercise
  onChanged: () => void
  onRest: (secs: number) => void
}) {
  const settings = useSettings()
  const prev = se.previous_performance
  const restSecs = se.rest_seconds ?? settings.default_rest_seconds

  async function addSet() {
    const idx = se.sets.length
    const ghost = prev?.sets[idx] ?? prev?.sets[prev.sets.length - 1]
    await api.logSet(session.id, se.id, {
      reps: ghost?.reps ?? se.target_reps ?? null,
      weight: ghost?.weight ?? null,
    })
    onRest(restSecs)
    onChanged()
  }

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
        <div className="grid grid-cols-[2rem_1fr_1fr_2rem] gap-2 px-1 text-xs uppercase text-slate-500">
          <span>Set</span>
          <span>{settings.weight_unit}</span>
          <span>Reps</span>
          <span />
        </div>
        {se.sets.map((s) => (
          <SetRow key={s.id} sessionId={session.id} seId={se.id} set={s} onChanged={onChanged} />
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

function SetRow({
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
  const [weight, setWeight] = useState(set.weight?.toString() ?? '')
  const [reps, setReps] = useState(set.reps?.toString() ?? '')

  const save = (patch: { weight?: number; reps?: number }) =>
    api.updateSet(sessionId, seId, set.id, patch)

  return (
    <div className="grid grid-cols-[2rem_1fr_1fr_2rem] items-center gap-2">
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
      <input
        type="number"
        inputMode="decimal"
        value={weight}
        onChange={(e) => setWeight(e.target.value)}
        onBlur={() => save({ weight: weight === '' ? undefined : Number(weight) })}
        className="rounded-lg bg-slate-800 px-3 py-2 text-center outline-none focus:ring-1 focus:ring-amber-500"
      />
      <input
        type="number"
        inputMode="numeric"
        value={reps}
        onChange={(e) => setReps(e.target.value)}
        onBlur={() => save({ reps: reps === '' ? undefined : Number(reps) })}
        className="rounded-lg bg-slate-800 px-3 py-2 text-center outline-none focus:ring-1 focus:ring-amber-500"
      />
      <button
        className="text-slate-600 hover:text-red-400"
        onClick={async () => {
          await api.deleteSet(sessionId, seId, set.id)
          onChanged()
        }}
      >
        ✕
      </button>
    </div>
  )
}
