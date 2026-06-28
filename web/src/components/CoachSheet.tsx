import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  api,
  type ActiveObjective,
  type ProgramPreview,
  type PlannedWorkoutPreview,
} from '../lib/api'
import { useVoiceInput } from '../lib/recorder'
import { Button, Sheet } from './ui'

const CREATE_PLACEHOLDER =
  'e.g. Run both my routines once a week for 8 weeks, ramping from 10 reps at a ' +
  'lighter weight to 3–5 reps heavy by the end. Add a deload in week 4.'
const MODIFY_PLACEHOLDER =
  'e.g. Shift everything a week later · make weeks 5–8 heavier · ' +
  'add a third day each week · I missed this week, push it back.'
// Used when an objective is active and the user generates without typing — the
// coach reads the objective + constraints server-side, so no detail is required.
const OBJECTIVE_DEFAULT_PROMPT = 'Build my training plan for this objective.'

function friendlyError(message: string): string {
  if (message.startsWith('503')) return "The AI coach isn't configured yet (no API key)."
  return message.replace(/^\d+:\s*/, '') // strip the "NNN: " status prefix from req()
}

function exerciseLine(
  e: PlannedWorkoutPreview['exercises'][number],
  unit: string,
): string {
  const sets = e.target_sets ?? '?'
  if (e.target_duration_seconds) return `${e.exercise_name} · ${sets}×${e.target_duration_seconds}s`
  const reps = e.target_reps ?? '?'
  const w = e.target_weight != null ? ` @ ${e.target_weight}${unit}` : ''
  return `${e.exercise_name} · ${sets}×${reps}${w}`
}

/**
 * The coach sheet doubles as create (no `program`) and modify (with `program`):
 * the FIRST request differs (generate vs modify-against-stored-spec), but a
 * refine is always a generate against the current preview's spec, and confirm
 * is save (create) vs apply (modify).
 */
export default function CoachSheet({
  open,
  onClose,
  onSaved,
  program,
  autoStart = false,
}: {
  open: boolean
  onClose: () => void
  onSaved: () => void
  program?: { id: number; name: string } | null
  // When opened from the objective tile's "Generate plan" CTA: kick off
  // generation automatically once the active objective has loaded.
  autoStart?: boolean
}) {
  const isModify = !!program
  const [message, setMessage] = useState('')
  const [refine, setRefine] = useState('')
  const [preview, setPreview] = useState<ProgramPreview | null>(null)
  const [modifyInfo, setModifyInfo] = useState<{ kept: number; future: number } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const voice = useVoiceInput((t) => setMessage((m) => (m ? m.trimEnd() + ' ' : '') + t))

  // The active objective (if any) — generation is automatically reverse-built to
  // peak/taper toward it and to train around the constraints (server-side).
  const { data: active } = useQuery({
    queryKey: ['active-objective'],
    queryFn: api.activeObjective,
    enabled: open && !isModify,
  })

  function close() {
    setMessage('')
    setRefine('')
    setPreview(null)
    setModifyInfo(null)
    setError(null)
    onClose()
  }

  const hasObjective = !isModify && !!active?.objective

  async function runInitial(text: string) {
    const trimmed = text.trim()
    if (isModify && program) {
      if (!trimmed) return
      setBusy(true)
      setError(null)
      try {
        const mp = await api.coachModifyProgram(program.id, trimmed)
        setPreview(mp.preview)
        setModifyInfo({ kept: mp.completed_preserved, future: mp.future_count })
      } catch (e) {
        setError(friendlyError((e as Error).message))
      } finally {
        setBusy(false)
      }
      return
    }
    // Create: with an active objective, a typed message is optional.
    const effective = trimmed || (hasObjective ? OBJECTIVE_DEFAULT_PROMPT : '')
    if (!effective) return
    setBusy(true)
    setError(null)
    try {
      setPreview(await api.coachGenerate(effective))
    } catch (e) {
      setError(friendlyError((e as Error).message))
    } finally {
      setBusy(false)
    }
  }

  // One-tap path: when launched from the objective tile, auto-generate as soon
  // as the active objective is known (fires once per open).
  const autoStarted = useRef(false)
  useEffect(() => {
    if (!open) {
      autoStarted.current = false
      return
    }
    if (autoStart && hasObjective && !preview && !busy && !autoStarted.current) {
      autoStarted.current = true
      void runInitial('')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, autoStart, hasObjective, preview, busy])

  async function refineWith(text: string, prior: ProgramPreview) {
    if (!text.trim()) return
    setBusy(true)
    setError(null)
    try {
      setPreview(await api.coachGenerate(text, prior.spec))
      setRefine('')
    } catch (e) {
      setError(friendlyError((e as Error).message))
    } finally {
      setBusy(false)
    }
  }

  async function confirm() {
    if (!preview) return
    setBusy(true)
    setError(null)
    try {
      if (isModify && program) {
        await api.coachApplyProgram(program.id, preview.spec, preview.name)
      } else {
        await api.coachSaveProgram(preview.spec, preview.name, message || undefined)
      }
      onSaved()
      close()
    } catch (e) {
      setError(friendlyError((e as Error).message))
    } finally {
      setBusy(false)
    }
  }

  const byWeek = new Map<number, PlannedWorkoutPreview[]>()
  preview?.planned_workouts.forEach((w) => {
    const k = w.week_index ?? 0
    byWeek.set(k, [...(byWeek.get(k) ?? []), w])
  })

  return (
    <Sheet open={open} onClose={close} title={isModify ? `Modify: ${program!.name}` : '✨ AI Coach'}>
      {!preview ? (
        <div className="space-y-3">
          {!isModify && active?.objective && <ObjectiveBanner active={active} />}
          <p className="text-sm text-slate-400">
            {isModify
              ? 'Describe the change. Completed workouts stay; future days are replanned.'
              : active?.objective
                ? 'The coach reverse-builds a periodized plan toward your objective (peaking and tapering to the date) and trains around your constraints. Add any extra detail below.'
                : 'Describe the program you want. The coach reads your routines and recent performance, then lays workouts onto your calendar with progression.'}
          </p>
          <div className="relative">
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={5}
              placeholder={isModify ? MODIFY_PLACEHOLDER : CREATE_PLACEHOLDER}
              className="w-full rounded-xl bg-slate-800 p-3 pr-14 text-sm outline-none focus:ring-1 focus:ring-amber-500"
            />
            {voice.supported && (
              <button
                type="button"
                onClick={voice.toggle}
                disabled={busy || voice.state === 'transcribing'}
                aria-label={voice.state === 'recording' ? 'Stop recording' : 'Speak'}
                className={`absolute bottom-2 right-2 flex h-10 w-10 items-center justify-center rounded-full text-lg disabled:opacity-50 ${
                  voice.state === 'recording'
                    ? 'animate-pulse bg-red-600 text-white'
                    : 'bg-slate-700 text-slate-200 hover:bg-slate-600'
                }`}
              >
                {voice.state === 'transcribing' ? '…' : voice.state === 'recording' ? '⏹' : '🎤'}
              </button>
            )}
          </div>
          {voice.state === 'recording' && (
            <p className="text-xs text-red-300">Listening… tap the square to stop.</p>
          )}
          {voice.error && <ErrBanner error={voice.error} />}
          {error && <ErrBanner error={error} />}
          <Button
            className="w-full"
            onClick={() => runInitial(message)}
            disabled={busy || (!message.trim() && !hasObjective)}
          >
            {busy ? 'Thinking…' : isModify ? 'Preview changes' : 'Generate plan'}
          </Button>
        </div>
      ) : (
        <div className="space-y-4">
          <p className="text-sm text-slate-200">{preview.coach_summary}</p>
          <p className="text-xs text-slate-500">
            {preview.planned_workouts.length} workouts · {preview.start_date} → {preview.end_date}
            {modifyInfo && ` · ${modifyInfo.kept} completed kept`}
          </p>

          {preview.created_routines.length > 0 && (
            <div className="rounded-xl border border-emerald-700/40 bg-emerald-900/15 px-3 py-2.5">
              <p className="text-xs font-semibold uppercase tracking-wide text-emerald-300">
                New routines the coach will create
              </p>
              <div className="mt-1.5 space-y-1.5">
                {preview.created_routines.map((r) => (
                  <div key={r.key}>
                    <div className="text-sm font-medium text-slate-100">{r.name}</div>
                    <div className="text-xs text-slate-400">{r.exercise_names.join(' · ')}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-3">
            {[...byWeek.entries()]
              .sort((a, b) => a[0] - b[0])
              .map(([week, workouts]) => (
                <div key={week}>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Week {week}
                  </p>
                  <div className="space-y-1.5">
                    {workouts.map((w, i) => (
                      <div key={i} className="rounded-lg border border-slate-800 bg-slate-800/40 px-3 py-2">
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-medium text-slate-100">{w.name}</span>
                          <span className="text-xs text-slate-500">{w.scheduled_date}</span>
                        </div>
                        <ul className="mt-1 space-y-0.5 text-xs text-slate-400">
                          {w.exercises.map((e, j) => (
                            <li key={j}>{exerciseLine(e, preview.weight_unit)}</li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
          </div>

          {error && <ErrBanner error={error} />}

          <div className="flex gap-2">
            <Button className="flex-1" onClick={confirm} disabled={busy}>
              {busy ? 'Saving…' : isModify ? 'Apply changes' : 'Add to calendar'}
            </Button>
            <Button variant="secondary" onClick={() => setPreview(null)} disabled={busy}>
              Back
            </Button>
          </div>

          <div className="border-t border-slate-800 pt-3">
            <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">Refine</p>
            <div className="flex gap-2">
              <input
                value={refine}
                onChange={(e) => setRefine(e.target.value)}
                placeholder="e.g. make week 4 a deload"
                className="flex-1 rounded-lg bg-slate-800 px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-amber-500"
              />
              <Button variant="secondary" onClick={() => refineWith(refine, preview)} disabled={busy || !refine.trim()}>
                Apply
              </Button>
            </div>
          </div>
        </div>
      )}
    </Sheet>
  )
}

function ErrBanner({ error }: { error: string }) {
  return (
    <p className="rounded-lg border border-red-800/50 bg-red-900/20 px-3 py-2 text-sm text-red-300">
      {error}
    </p>
  )
}

function formatTarget(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  const date = d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
  const weeks = Math.max(0, Math.round((d.getTime() - Date.now()) / (7 * 864e5)))
  return `${date} · ~${weeks} wk${weeks === 1 ? '' : 's'} out`
}

function ObjectiveBanner({ active }: { active: ActiveObjective }) {
  const o = active.objective!
  return (
    <div className="rounded-xl border border-amber-700/40 bg-amber-900/15 px-3 py-2.5">
      <div className="flex items-center gap-2 text-sm font-semibold text-amber-200">
        <span>🎯</span>
        <span className="truncate">Building toward: {o.name}</span>
      </div>
      {o.kind === 'dated' && o.target_date && (
        <p className="mt-0.5 text-xs text-amber-300/80">{formatTarget(o.target_date)}</p>
      )}
      {active.constraints.length > 0 && (
        <p className="mt-1 text-xs text-slate-400">
          Training around:{' '}
          {active.constraints.map((c, i) => (
            <span key={c.id}>
              {i > 0 && ', '}
              {c.label}
              {c.defer_to_professional && <span className="text-slate-500"> (defer to PT)</span>}
            </span>
          ))}
        </p>
      )}
    </div>
  )
}
