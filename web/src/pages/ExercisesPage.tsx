import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { Button, Card, EmptyState, PageTitle, Spinner } from '../components/ui'
import ExercisePicker from '../components/ExercisePicker'

export default function ExercisesPage() {
  const [q, setQ] = useState('')
  const [debounced, setDebounced] = useState('')
  const [pickerOpen, setPickerOpen] = useState(false)

  useEffect(() => {
    const id = setTimeout(() => setDebounced(q.trim()), 250)
    return () => clearTimeout(id)
  }, [q])

  const { data: hits = [], isFetching } = useQuery({
    queryKey: ['exerciseSearch', debounced, 40],
    queryFn: () => api.searchExercises(debounced, 40),
    enabled: debounced.length > 0,
  })

  return (
    <div>
      <PageTitle right={<Button onClick={() => setPickerOpen(true)}>New</Button>}>Library</PageTitle>

      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search by name, abbreviation, or description…"
        className="w-full rounded-xl border border-slate-700 bg-slate-800 px-4 py-3 text-base outline-none focus:border-amber-500"
      />

      {isFetching ? (
        <Spinner />
      ) : debounced === '' ? (
        <EmptyState title="Search the exercise library" hint="e.g. “RDL”, “overhead press”, or “hamstring curl lying down”." />
      ) : hits.length === 0 ? (
        <EmptyState title="No matches" hint="Tap “New” to add it to your library." />
      ) : (
        <div className="mt-3 space-y-2">
          {hits.map((h) => (
            <Card key={h.exercise.id}>
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-100">{h.exercise.name}</span>
                {h.exercise.provenance !== 'canonical' && (
                  <span className="rounded bg-slate-700 px-1.5 py-0.5 text-[10px] uppercase text-slate-300">
                    {h.exercise.provenance}
                  </span>
                )}
              </div>
              <div className="mt-0.5 text-xs text-slate-400">
                {[h.exercise.primary_muscles?.join(', '), h.exercise.equipment, h.exercise.mechanic]
                  .filter(Boolean)
                  .join(' · ')}
              </div>
              {h.exercise.aliases.length > 0 && (
                <div className="mt-1 text-xs text-slate-500">aka {h.exercise.aliases.join(', ')}</div>
              )}
            </Card>
          ))}
        </div>
      )}

      {/* Reuse the picker purely to add to the catalog (selection is a no-op here). */}
      <ExercisePicker open={pickerOpen} onClose={() => setPickerOpen(false)} onSelect={() => {}} />
    </div>
  )
}
