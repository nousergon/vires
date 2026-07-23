import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, type ExerciseBrief, type ExerciseSuggestion } from '../lib/api'
import { EmptyState, Sheet, Spinner } from './ui'

// Swap an in-progress exercise for a similar one in a single tap. Opens on a
// ranked list of substitutes (movement-pattern + target-muscle matches from
// the backend) so the common case — "give me something like this" — is one
// tap, with a search box to fall back to any exercise. Replacing keeps the
// move's slot in the sequence, so there's no remove + re-add + drag-back.
export default function ReplaceExerciseSheet({
  open,
  onClose,
  exercise,
  onReplace,
}: {
  open: boolean
  onClose: () => void
  exercise: ExerciseBrief
  onReplace: (ex: ExerciseBrief) => void
}) {
  const [q, setQ] = useState('')
  const [debounced, setDebounced] = useState('')

  useEffect(() => {
    const id = setTimeout(() => setDebounced(q.trim()), 250)
    return () => clearTimeout(id)
  }, [q])

  // Reset the search box each time the sheet re-opens.
  useEffect(() => {
    if (open) {
      setQ('')
      setDebounced('')
    }
  }, [open])

  const { data: suggestions = [], isLoading } = useQuery({
    queryKey: ['similarExercises', exercise.id],
    queryFn: () => api.similarExercises(exercise.id),
    enabled: open,
  })

  const { data: hits = [], isFetching } = useQuery({
    queryKey: ['exerciseSearch', debounced, 6],
    queryFn: () => api.searchExercises(debounced, 6),
    enabled: open && debounced.length > 0,
  })

  function pick(ex: ExerciseBrief) {
    onReplace(ex)
    onClose()
  }

  const searching = debounced.length > 0

  return (
    <Sheet open={open} onClose={onClose} title={`Replace ${exercise.name}`}>
      <input
        autoFocus
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Or search for any exercise…"
        className="w-full rounded-xl border border-slate-700 bg-slate-800 px-4 py-3 text-base outline-none focus:border-amber-500"
      />

      {searching ? (
        <>
          {isFetching && <Spinner />}
          <ul className="mt-3 space-y-1">
            {hits
              .filter((h) => h.exercise.id !== exercise.id)
              .map((h) => (
                <li key={h.exercise.id}>
                  <button
                    onClick={() => pick(h.exercise)}
                    className="w-full rounded-xl px-3 py-3 text-left hover:bg-slate-800"
                  >
                    <div className="font-medium text-slate-100">{h.exercise.name}</div>
                    <div className="text-xs text-slate-400">
                      {[h.exercise.primary_muscles?.join(', '), h.exercise.equipment]
                        .filter(Boolean)
                        .join(' · ')}
                    </div>
                  </button>
                </li>
              ))}
          </ul>
          {!isFetching && hits.filter((h) => h.exercise.id !== exercise.id).length === 0 && (
            <EmptyState title="No matches" hint="Try a different search." />
          )}
        </>
      ) : (
        <>
          <div className="mb-1 mt-4 text-xs font-semibold uppercase tracking-wide text-slate-400">
            Similar exercises
          </div>
          {isLoading ? (
            <Spinner />
          ) : suggestions.length === 0 ? (
            <EmptyState title="No similar exercises" hint="Search above to pick a replacement." />
          ) : (
            <ul className="space-y-1">
              {suggestions.map((s) => (
                <li key={s.exercise.id}>
                  <button
                    onClick={() => pick(s.exercise)}
                    className="flex w-full items-center justify-between gap-2 rounded-xl px-3 py-3 text-left hover:bg-slate-800"
                  >
                    <span className="min-w-0">
                      <span className="block font-medium text-slate-100">{s.exercise.name}</span>
                      <span className="block text-xs text-slate-400">
                        {[s.exercise.primary_muscles?.join(', '), s.exercise.equipment]
                          .filter(Boolean)
                          .join(' · ')}
                      </span>
                    </span>
                    <VerdictBadge verdict={s.verdict} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </Sheet>
  )
}

function VerdictBadge({ verdict }: { verdict: ExerciseSuggestion['verdict'] }) {
  const equivalent = verdict === 'equivalent'
  return (
    <span
      className={`shrink-0 rounded-full border px-2 py-0.5 text-xs ${
        equivalent
          ? 'border-emerald-700/60 bg-emerald-900/30 text-emerald-200'
          : 'border-sky-700/60 bg-sky-900/30 text-sky-200'
      }`}
    >
      {equivalent ? 'Equivalent' : 'Comparable'}
    </span>
  )
}
