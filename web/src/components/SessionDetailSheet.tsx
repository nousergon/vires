import { useState, type FocusEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  api,
  type ActivityDetail,
  type SessionExercise,
  type SetEntry,
  type WeightUnit,
  type WorkoutSession,
} from '../lib/api'
import { useSettings } from '../lib/useSettings'
import { fmtClock } from '../lib/timer'
import { fmtDistance, fmtElevation, fmtLoad, fmtPack } from '../lib/units'
import { Button, Sheet, Spinner } from './ui'

const selectOnFocus = (e: FocusEvent<HTMLInputElement>) => e.currentTarget.select()

// One-line summary of an activity's headline facts. A route-capable entry
// with a distance leads with pack (if any)/distance/load; everything else
// falls back to duration · regions · intensity. Shared by the History list
// rows and this sheet.
export function activityLine(activity: ActivityDetail, unit: WeightUnit): string {
  const parts =
    activity.distance_m != null || activity.pack_weight_kg != null
      ? [
          activity.pack_weight_kg != null ? fmtPack(activity.pack_weight_kg, unit) : null,
          fmtDistance(activity.distance_m, unit),
          fmtLoad(activity.metabolic_cost_kj),
        ]
      : [
          activity.duration_s != null ? fmtClock(activity.duration_s) : null,
          activity.regions !== 'none' ? activity.regions : null,
          activity.intensity,
        ]
  return parts.filter(Boolean).join(' · ')
}

// A 1–10 tap scale. `null` = not rated. (Moved from WorkoutPage so the
// finish prompt and the after-the-fact editor render the identical control.)
export function RatingScale({
  label,
  hint,
  value,
  onChange,
}: {
  label: string
  hint: string
  value: number | null
  onChange: (v: number | null) => void
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-semibold text-slate-100">{label}</span>
        <span className="text-xs text-slate-500">{value == null ? hint : `${value} / 10`}</span>
      </div>
      <div className="mt-2 grid grid-cols-10 gap-1">
        {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
          <button
            key={n}
            type="button"
            aria-label={`${label} ${n}`}
            aria-pressed={value === n}
            onClick={() => onChange(value === n ? null : n)}
            className={`rounded-md py-2 text-xs font-semibold transition ${
              value != null && n <= value
                ? 'bg-amber-500 text-slate-950'
                : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
            }`}
          >
            {n}
          </button>
        ))}
      </div>
    </div>
  )
}

// Freeform reusable/one-off tag pills with inline add. Persist via `onSave`.
export function TagsEditor({
  tags,
  onSave,
}: {
  tags: string[]
  onSave: (tags: string[]) => void
}) {
  const [draft, setDraft] = useState('')

  function addTag() {
    const t = draft.trim()
    setDraft('')
    if (!t || tags.includes(t)) return
    onSave([...tags, t])
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {tags.map((t) => (
        <span
          key={t}
          className="inline-flex items-center gap-1 rounded-full border border-amber-600/50 bg-amber-900/30 px-2.5 py-0.5 text-xs text-amber-200"
        >
          {t}
          <button
            type="button"
            aria-label={`Remove tag ${t}`}
            className="text-amber-300/70 hover:text-amber-100"
            onClick={() => onSave(tags.filter((x) => x !== t))}
          >
            ✕
          </button>
        </span>
      ))}
      <input
        type="text"
        value={draft}
        placeholder="+ add tag"
        onChange={(e) => setDraft(e.target.value)}
        onBlur={addTag}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            addTag()
          }
        }}
        className="min-w-[6rem] flex-1 rounded-lg bg-slate-800 px-2 py-1 text-xs outline-none focus:ring-1 focus:ring-amber-500"
      />
    </div>
  )
}

// What was eaten/drunk/supplemented before training — persists on blur.
export function FuelField({
  value,
  onSave,
}: {
  value: string | null
  onSave: (fuel: string | null) => void
}) {
  const [fuel, setFuel] = useState(value ?? '')
  return (
    <textarea
      value={fuel}
      rows={2}
      placeholder="e.g. black coffee, 5g creatine, banana"
      onChange={(e) => setFuel(e.target.value)}
      onBlur={() => {
        if ((fuel.trim() || null) !== (value ?? null)) onSave(fuel.trim() || null)
      }}
      className="mt-1 w-full resize-none rounded-lg bg-slate-800 px-2.5 py-2 text-sm outline-none focus:ring-1 focus:ring-amber-500"
    />
  )
}

// Editable session-tracking block: tags, pre-workout fuel, and the 1–10
// energy/intensity self-report — every field revisable AFTER the workout,
// not only at the finish prompt. Each change persists immediately via
// PATCH /workouts/{id}.
function SessionTrackingEditor({
  session,
  onChanged,
}: {
  session: WorkoutSession
  onChanged: () => void
}) {
  const save = async (body: Parameters<typeof api.updateWorkout>[1]) => {
    await api.updateWorkout(session.id, body)
    onChanged()
  }

  return (
    <div className="space-y-4">
      <div>
        <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
          Tags
        </div>
        <TagsEditor tags={session.tags} onSave={(tags) => save({ tags })} />
      </div>
      <div>
        <label className="block text-xs font-semibold uppercase tracking-wide text-slate-400">
          Pre-workout food / drink / supps
        </label>
        <FuelField
          value={session.pre_workout_fuel}
          onSave={(pre_workout_fuel) => save({ pre_workout_fuel })}
        />
      </div>
      <RatingScale
        label="Energy level"
        hint="How did your body feel?"
        value={session.energy_level}
        onChange={(v) => save({ energy_level: v })}
      />
      <RatingScale
        label="Workout intensity"
        hint="How hard was this session?"
        value={session.workout_intensity}
        onChange={(v) => save({ workout_intensity: v })}
      />
    </div>
  )
}

// Editable weight/reps for a set already logged in a finished workout — the
// after-the-fact counterpart to WorkoutPage's in-workout SetRow, minus the
// live-timer/mark-done affordances that don't apply to a closed session.
function SetEditRow({
  sessionId,
  se,
  set,
  onSaved,
}: {
  sessionId: number
  se: SessionExercise
  set: SetEntry
  onSaved: () => void
}) {
  const [weight, setWeight] = useState(set.weight?.toString() ?? '')
  const [reps, setReps] = useState(set.reps?.toString() ?? '')

  const save = async (patch: { weight?: number; reps?: number }) => {
    await api.updateSet(sessionId, se.id, set.id, patch)
    onSaved()
  }

  const cell =
    'w-full min-w-0 rounded-lg bg-slate-800 px-2 py-1.5 text-center outline-none focus:ring-1 focus:ring-amber-500'

  return (
    <div className="grid grid-cols-[1.5rem_1fr_1fr] items-center gap-2">
      <span className="text-slate-500">{set.is_warmup ? 'W' : set.set_number}</span>
      <input
        type="number"
        inputMode="decimal"
        aria-label={`${se.exercise.name} set ${set.set_number} weight`}
        value={weight}
        onFocus={selectOnFocus}
        onChange={(e) => setWeight(e.target.value)}
        onBlur={() => save({ weight: weight === '' ? undefined : Number(weight) })}
        className={cell}
      />
      <input
        type="number"
        inputMode="numeric"
        aria-label={`${se.exercise.name} set ${set.set_number} reps`}
        value={reps}
        onFocus={selectOnFocus}
        onChange={(e) => setReps(e.target.value)}
        onBlur={() => save({ reps: reps === '' ? undefined : Number(reps) })}
        className={cell}
      />
    </div>
  )
}

// The one detail surface for a logged session, shared by History and the Plan
// day-sheet: date, editable tracking (tags / fuel / ratings), activity facts,
// exercises with after-the-fact set editing, and delete.
export default function SessionDetailSheet({
  sessionId,
  onClose,
  onDeleted,
}: {
  sessionId: number | null
  onClose: () => void
  // Optional extra hook after a successful delete (the sheet closes itself).
  onDeleted?: () => void
}) {
  const qc = useQueryClient()
  const unit = useSettings().weight_unit
  const [editingSets, setEditingSets] = useState(false)
  const [busy, setBusy] = useState(false)

  const { data: detail, isLoading } = useQuery({
    queryKey: ['workout', sessionId],
    queryFn: () => api.getWorkout(sessionId as number),
    enabled: sessionId != null,
  })

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['workout', sessionId] })
    qc.invalidateQueries({ queryKey: ['workouts'] })
    qc.invalidateQueries({ queryKey: ['records'] })
    qc.invalidateQueries({ queryKey: ['calendar'] })
  }

  async function deleteOne(id: number) {
    if (!confirm("Delete this workout from history? This can't be undone.")) return
    setBusy(true)
    try {
      await api.deleteWorkout(id)
      refresh()
      onClose()
      onDeleted?.()
    } catch (e) {
      alert(`Couldn't delete: ${(e as Error).message.replace(/^\d+:\s*/, '')}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet
      open={sessionId != null}
      onClose={() => {
        setEditingSets(false)
        onClose()
      }}
      title={detail?.name || 'Workout'}
    >
      {isLoading || !detail ? (
        <Spinner />
      ) : (
        <div className="space-y-4">
          <p className="text-sm text-slate-400">{new Date(detail.started_at).toLocaleString()}</p>
          <SessionTrackingEditor session={detail} onChanged={refresh} />
          {detail.session_type === 'activity' && detail.activity && (
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Duration</dt>
                <dd className="text-slate-200">
                  {detail.activity.duration_s != null ? fmtClock(detail.activity.duration_s) : '—'}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Intensity</dt>
                <dd className="capitalize text-slate-200">{detail.activity.intensity}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Regions worked</dt>
                <dd className="capitalize text-slate-200">{detail.activity.regions}</dd>
              </div>
              {/* Route rows for any route-capable entry with a distance logged. */}
              {detail.activity.distance_m != null && (
                <>
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-slate-500">Distance</dt>
                    <dd className="text-slate-200">
                      {fmtDistance(detail.activity.distance_m, unit) ?? '—'}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-slate-500">
                      Elevation gain
                    </dt>
                    <dd className="text-slate-200">
                      {fmtElevation(detail.activity.elevation_gain_m, unit) ?? '—'}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-slate-500">Terrain</dt>
                    <dd className="capitalize text-slate-200">{detail.activity.terrain}</dd>
                  </div>
                </>
              )}
              {/* Pack/load rows only when a pack weight was actually logged. */}
              {detail.activity.pack_weight_kg != null && (
                <>
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-slate-500">Pack</dt>
                    <dd className="font-semibold text-slate-100">
                      {fmtPack(detail.activity.pack_weight_kg, unit)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-slate-500">Load</dt>
                    <dd className="font-semibold text-amber-400">
                      {fmtLoad(detail.activity.metabolic_cost_kj) ?? '—'}
                    </dd>
                  </div>
                </>
              )}
            </dl>
          )}
          {detail.exercises.length > 0 && (
            <div className="flex justify-end">
              <button
                className="text-sm text-amber-300 hover:text-amber-200"
                onClick={() => setEditingSets((v) => !v)}
              >
                {editingSets ? 'Done editing' : 'Edit sets'}
              </button>
            </div>
          )}
          {detail.exercises.map((se) => (
            <div key={se.id}>
              <h3 className="font-semibold text-slate-100">{se.exercise.name}</h3>
              {editingSets ? (
                <div className="mt-1 space-y-1">
                  {se.sets.map((s) => (
                    <SetEditRow
                      key={s.id}
                      sessionId={detail.id}
                      se={se}
                      set={s}
                      onSaved={refresh}
                    />
                  ))}
                  {se.sets.length === 0 && <p className="text-sm text-slate-500">no sets logged</p>}
                </div>
              ) : (
                <ul className="mt-1 text-sm text-slate-300">
                  {se.sets.map((s) => (
                    <li key={s.id} className="flex gap-2">
                      <span className="w-6 text-slate-500">{s.is_warmup ? 'W' : s.set_number}</span>
                      <span>
                        {s.weight ?? '—'} × {s.reps ?? '—'}
                        {s.rpe ? ` @ RPE ${s.rpe}` : ''}
                      </span>
                    </li>
                  ))}
                  {se.sets.length === 0 && <li className="text-slate-500">no sets logged</li>}
                </ul>
              )}
            </div>
          ))}
          <div className="border-t border-slate-800 pt-3">
            <Button
              variant="danger"
              className="w-full"
              onClick={() => deleteOne(detail.id)}
              disabled={busy}
            >
              {busy ? 'Deleting…' : 'Delete workout'}
            </Button>
          </div>
        </div>
      )}
    </Sheet>
  )
}
