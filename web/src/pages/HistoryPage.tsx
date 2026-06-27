import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, type WorkoutSession } from '../lib/api'
import { Card, EmptyState, PageTitle, Sheet, Spinner } from '../components/ui'

export default function HistoryPage() {
  const { data: workouts = [], isLoading } = useQuery({
    queryKey: ['workouts'],
    queryFn: api.listWorkouts,
  })
  const [detail, setDetail] = useState<WorkoutSession | null>(null)

  return (
    <div>
      <PageTitle>History</PageTitle>
      {isLoading ? (
        <Spinner />
      ) : workouts.length === 0 ? (
        <EmptyState title="No workouts yet" hint="Your finished workouts show up here." />
      ) : (
        <div className="space-y-2">
          {workouts.map((w) => (
            <Card key={w.id}>
              <button
                className="w-full text-left"
                onClick={async () => setDetail(await api.getWorkout(w.id))}
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-slate-100">{w.name || 'Workout'}</span>
                  <span className="text-xs text-slate-400">
                    {new Date(w.started_at).toLocaleDateString()}
                  </span>
                </div>
                <div className="mt-1 text-xs text-slate-400">
                  {w.exercise_count} exercises · {w.set_count} sets
                  {w.total_volume > 0 && ` · ${w.total_volume.toLocaleString()} vol`}
                  {!w.ended_at && <span className="ml-2 text-amber-400">in progress</span>}
                </div>
              </button>
            </Card>
          ))}
        </div>
      )}

      <Sheet open={!!detail} onClose={() => setDetail(null)} title={detail?.name || 'Workout'}>
        {detail && (
          <div className="space-y-4">
            <p className="text-sm text-slate-400">
              {new Date(detail.started_at).toLocaleString()}
            </p>
            {detail.exercises.map((se) => (
              <div key={se.id}>
                <h3 className="font-semibold text-slate-100">{se.exercise.name}</h3>
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
              </div>
            ))}
          </div>
        )}
      </Sheet>
    </div>
  )
}
