import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type Exercise, type ExerciseBrief, type ExerciseSuggestion } from '../lib/api'
import { reportWriteFailure } from '../lib/writeFailure'
import { Sheet, Spinner } from './ui'

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
  const [creating, setCreating] = useState(false)
  const qc = useQueryClient()

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

  const brief = (ex: Exercise): ExerciseBrief => ({
    id: ex.id,
    name: ex.name,
    primary_muscles: ex.primary_muscles,
    equipment: ex.equipment,
    is_timed: ex.is_timed,
    movement_pattern: ex.movement_pattern,
  })

  // Search never returns an empty list for a plausible query — it is a hybrid
  // BM25 + vector retriever, so "hanging knee raise" ranks Hanging Leg Raise,
  // Bent-Knee Hip Raise and Knee/Hip Raise On Parallel Bars rather than
  // nothing. The "No matches" empty state this replaces was therefore almost
  // unreachable, and without a create path the sheet was a DEAD END for any
  // move outside the 873-exercise seed catalog: plausible-but-wrong results,
  // an "add new" affordance that existed only in the add-exercise picker, and
  // no way to reach it without backing out of the swap entirely. Reported
  // 2026-08-03 trying to swap Hanging Leg Raise for a Hanging Knee Raise,
  // which the catalog does not contain. Mirrors ExercisePicker's create
  // affordance rather than inventing a second one; `force: false` keeps the
  // server's exact-duplicate guard, and an exact duplicate is simply used.
  async function createAndUse() {
    const name = debounced
    setCreating(true)
    try {
      const res = await api.createExercise({ name, force: false })
      const chosen = res.created && res.exercise ? res.exercise : res.duplicate_of
      if (!chosen) {
        reportWriteFailure(`add “${name}”`, new Error('the server returned no exercise'))
        return
      }
      qc.invalidateQueries({ queryKey: ['exerciseSearch'] })
      pick(brief(chosen))
    } catch (err) {
      reportWriteFailure(`add “${name}”`, err)
    } finally {
      setCreating(false)
    }
  }

  const searching = debounced.length > 0
  const results = hits.filter((h) => h.exercise.id !== exercise.id)
  // An exact name match means it already exists; offering "add it" there would
  // only produce the server's duplicate prompt.
  const exactMatch = hits.some((h) => h.exercise.name.toLowerCase() === debounced.toLowerCase())

  return (
    <Sheet open={open} onClose={onClose} title={`Replace ${exercise.name}`}>
      <input
        autoFocus
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Or search for any exercise…"
        // type="search" plus these: without them iOS Safari cannot classify the
        // field and shows its AutoFill accessory bar (passwords / credit cards
        // / contacts) over the results list — which reads as the app asking for
        // credentials. Autocorrect and auto-capitalisation are wrong for
        // exercise names anyway ("RDL", "3/4 sit-up").
        type="search"
        name="exercise-search"
        autoComplete="off"
        autoCorrect="off"
        autoCapitalize="none"
        spellCheck={false}
        enterKeyHint="search"
        className="w-full rounded-xl border border-slate-700 bg-slate-800 px-4 py-3 text-base outline-none focus:border-amber-500"
      />

      {searching ? (
        <>
          {isFetching && <Spinner />}
          <ul className="mt-3 space-y-1">
            {results.map((h) => (
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
          {!isFetching && !exactMatch && (
            <button
              disabled={creating}
              onClick={createAndUse}
              className="mt-3 w-full rounded-xl border border-dashed border-slate-600 px-3 py-3 text-left text-slate-300 hover:bg-slate-800 disabled:opacity-40"
            >
              ➕ Add <span className="font-semibold">“{debounced}”</span> and use it here
            </button>
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
            <p className="py-8 text-center text-sm text-slate-400">
              No similar exercises — search above to pick a replacement.
            </p>
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
