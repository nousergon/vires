import { useState } from 'react'
import { api, type ProgramPreview, type PlannedWorkoutPreview } from '../lib/api'
import { Button, Sheet } from './ui'

const PLACEHOLDER =
  'e.g. Run both my routines once a week for 8 weeks, ramping from 10 reps at a ' +
  'lighter weight to 3–5 reps heavy by the end. Add a deload in week 4.'

function friendlyError(message: string): string {
  if (message.startsWith('503')) return "The AI coach isn't configured yet (no API key)."
  // strip the leading "NNN: " status prefix from req()
  return message.replace(/^\d+:\s*/, '')
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

export default function CoachSheet({
  open,
  onClose,
  onSaved,
}: {
  open: boolean
  onClose: () => void
  onSaved: () => void
}) {
  const [message, setMessage] = useState('')
  const [refine, setRefine] = useState('')
  const [preview, setPreview] = useState<ProgramPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function close() {
    setMessage('')
    setRefine('')
    setPreview(null)
    setError(null)
    onClose()
  }

  async function generate(text: string, prior?: ProgramPreview | null) {
    if (!text.trim()) return
    setBusy(true)
    setError(null)
    try {
      const p = await api.coachGenerate(text, prior?.spec)
      setPreview(p)
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
      await api.coachSaveProgram(preview.spec, preview.name, message || undefined)
      onSaved()
      close()
    } catch (e) {
      setError(friendlyError((e as Error).message))
    } finally {
      setBusy(false)
    }
  }

  // group the preview's workouts by week for a scannable plan view
  const byWeek = new Map<number, PlannedWorkoutPreview[]>()
  preview?.planned_workouts.forEach((w) => {
    const k = w.week_index ?? 0
    byWeek.set(k, [...(byWeek.get(k) ?? []), w])
  })

  return (
    <Sheet open={open} onClose={close} title="✨ AI Coach">
      {!preview ? (
        <div className="space-y-3">
          <p className="text-sm text-slate-400">
            Describe the program you want. The coach reads your routines and recent
            performance, then lays workouts onto your calendar with progression.
          </p>
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            rows={5}
            placeholder={PLACEHOLDER}
            className="w-full rounded-xl bg-slate-800 p-3 text-sm outline-none focus:ring-1 focus:ring-amber-500"
          />
          {error && <ErrBanner error={error} />}
          <Button
            className="w-full"
            onClick={() => generate(message)}
            disabled={busy || !message.trim()}
          >
            {busy ? 'Thinking…' : 'Generate plan'}
          </Button>
        </div>
      ) : (
        <div className="space-y-4">
          <p className="text-sm text-slate-200">{preview.coach_summary}</p>
          <p className="text-xs text-slate-500">
            {preview.planned_workouts.length} workouts · {preview.start_date} →{' '}
            {preview.end_date}
          </p>

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
                      <div
                        key={i}
                        className="rounded-lg border border-slate-800 bg-slate-800/40 px-3 py-2"
                      >
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
              {busy ? 'Saving…' : 'Add to calendar'}
            </Button>
            <Button variant="secondary" onClick={() => setPreview(null)} disabled={busy}>
              Back
            </Button>
          </div>

          <div className="border-t border-slate-800 pt-3">
            <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Refine
            </p>
            <div className="flex gap-2">
              <input
                value={refine}
                onChange={(e) => setRefine(e.target.value)}
                placeholder="e.g. make week 4 a deload"
                className="flex-1 rounded-lg bg-slate-800 px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-amber-500"
              />
              <Button
                variant="secondary"
                onClick={() => generate(refine, preview)}
                disabled={busy || !refine.trim()}
              >
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
