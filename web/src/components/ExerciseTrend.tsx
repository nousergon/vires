import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, type ExerciseBrief } from '../lib/api'
import { useSettings } from '../lib/useSettings'
import { fmtClock } from '../lib/timer'
import { Button, Card, EmptyState, Spinner } from './ui'
import ExercisePicker from './ExercisePicker'
import { TrendChart, type TrendPoint } from './TrendChart'

const WINDOWS = [10, 20, 30] as const

// Per-exercise trend chart: max weight (or, for a timed exercise, longest
// hold) per session over the last N sessions — the raw per-session sets come
// from the existing GET /exercises/{id}/history endpoint; the per-session
// aggregation happens here rather than server-side since it's a handful of
// sets per session, not worth a dedicated backend query.
export default function ExerciseTrend() {
  const unit = useSettings().weight_unit
  const [exercise, setExercise] = useState<ExerciseBrief | null>(null)
  const [limit, setLimit] = useState<(typeof WINDOWS)[number]>(10)
  const [pickerOpen, setPickerOpen] = useState(false)

  const { data: history = [], isLoading } = useQuery({
    queryKey: ['exerciseHistory', exercise?.id, limit],
    queryFn: () => api.exerciseHistory(exercise!.id, limit),
    enabled: exercise != null,
  })

  const points: TrendPoint[] = [...history]
    // The API returns most-recent-first; the chart reads oldest -> newest,
    // left to right.
    .reverse()
    .map((session) => {
      const working = session.sets.filter((s) => !s.is_warmup)
      const metric = exercise?.is_timed
        ? Math.max(0, ...working.map((s) => s.duration_seconds ?? 0))
        : Math.max(0, ...working.map((s) => s.weight ?? 0))
      return { session, metric }
    })
    // Sessions with no working sets carrying the metric we're charting
    // (e.g. only warmups logged, or a bodyweight-only exercise with no
    // weight entered) have nothing to plot.
    .filter(({ metric }) => metric > 0)
    .map(({ session, metric }) => ({
      x: new Date(session.date).toLocaleDateString(undefined, { month: 'numeric', day: 'numeric' }),
      value: metric,
      displayValue: exercise?.is_timed ? fmtClock(Math.round(metric)) : `${metric}`,
      tooltip: `${session.session_name ?? 'Workout'} — ${new Date(session.date).toLocaleDateString()}`,
    }))

  const skippedCount = history.length - points.length

  return (
    <div>
      <Button variant="secondary" className="w-full" onClick={() => setPickerOpen(true)}>
        {exercise ? exercise.name : 'Choose an exercise'}
      </Button>

      {exercise && (
        <>
          <div className="my-3 flex gap-1.5">
            {WINDOWS.map((w) => (
              <button
                key={w}
                onClick={() => setLimit(w)}
                className={`flex-1 rounded-lg border py-1.5 text-xs font-medium ${
                  limit === w
                    ? 'border-amber-500 bg-amber-500/10 text-amber-300'
                    : 'border-slate-700 text-slate-400'
                }`}
              >
                Last {w}
              </button>
            ))}
          </div>

          {isLoading ? (
            <Spinner />
          ) : points.length === 0 ? (
            <EmptyState
              title="No logged sets yet"
              hint="Log some working sets for this exercise to see a trend."
            />
          ) : (
            <Card>
              <div className="mb-2 flex items-baseline justify-between">
                <span className="text-xs uppercase tracking-wide text-slate-500">
                  {exercise.is_timed ? 'Longest hold per session' : `Max weight per session (${unit})`}
                </span>
                {points.length > 1 && (
                  <span className="text-xs text-slate-400">{points.length} sessions</span>
                )}
              </div>
              <TrendChart points={points} />
              {skippedCount > 0 && (
                <p className="mt-2 text-[11px] text-slate-500">
                  {skippedCount} session{skippedCount === 1 ? '' : 's'} skipped (no working sets logged)
                </p>
              )}
            </Card>
          )}
        </>
      )}

      <ExercisePicker open={pickerOpen} onClose={() => setPickerOpen(false)} onSelect={setExercise} />
    </div>
  )
}
