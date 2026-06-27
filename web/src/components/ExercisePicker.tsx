import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type CreateResult, type Exercise, type ExerciseBrief } from '../lib/api'
import { Button, Sheet, Spinner } from './ui'

export default function ExercisePicker({
  open,
  onClose,
  onSelect,
}: {
  open: boolean
  onClose: () => void
  onSelect: (ex: ExerciseBrief) => void
}) {
  const [q, setQ] = useState('')
  const [debounced, setDebounced] = useState('')
  const [suggestion, setSuggestion] = useState<CreateResult | null>(null)
  const [creating, setCreating] = useState(false)
  const qc = useQueryClient()

  useEffect(() => {
    const id = setTimeout(() => setDebounced(q.trim()), 250)
    return () => clearTimeout(id)
  }, [q])

  // reset transient state whenever the sheet re-opens
  useEffect(() => {
    if (open) {
      setQ('')
      setDebounced('')
      setSuggestion(null)
    }
  }, [open])

  // Just the closest few: a short list makes "nothing matches → add new" obvious.
  const LIMIT = 6
  const { data: hits = [], isFetching } = useQuery({
    queryKey: ['exerciseSearch', debounced, LIMIT],
    queryFn: () => api.searchExercises(debounced, LIMIT),
    enabled: open && debounced.length > 0,
  })

  function pick(ex: ExerciseBrief) {
    onSelect(ex)
    onClose()
  }

  async function create(force: boolean) {
    setCreating(true)
    try {
      const res = await api.createExercise({ name: q.trim(), force })
      if (res.created && res.exercise) {
        qc.invalidateQueries({ queryKey: ['exerciseSearch'] })
        pick(res.exercise)
      } else {
        setSuggestion(res) // exact / similar -> ask the user
      }
    } finally {
      setCreating(false)
    }
  }

  const exact = (ex: Exercise) => ({
    id: ex.id,
    name: ex.name,
    primary_muscles: ex.primary_muscles,
    equipment: ex.equipment,
    is_timed: ex.is_timed,
  })

  return (
    <Sheet open={open} onClose={onClose} title="Add exercise">
      <input
        autoFocus
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search e.g. RDL, bench press, or describe it…"
        className="w-full rounded-xl border border-slate-700 bg-slate-800 px-4 py-3 text-base outline-none focus:border-amber-500"
      />

      {suggestion && suggestion.duplicate_of && (
        <div className="mt-3 rounded-xl border border-amber-700/50 bg-amber-900/20 p-3 text-sm">
          <p className="text-amber-200">
            {suggestion.reason === 'exact' ? 'Already in your library:' : 'Did you mean'}{' '}
            <span className="font-semibold">{suggestion.duplicate_of.name}</span>
            {suggestion.reason === 'similar' ? '?' : ''}
          </p>
          <div className="mt-2 flex gap-2">
            <Button onClick={() => pick(exact(suggestion.duplicate_of!))}>Use it</Button>
            <Button variant="secondary" disabled={creating} onClick={() => create(true)}>
              Create “{q.trim()}” anyway
            </Button>
          </div>
        </div>
      )}

      {isFetching && <Spinner />}

      <ul className="mt-3 space-y-1">
        {hits.map((h) => (
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

      {debounced && !isFetching && !suggestion && (
        <button
          disabled={creating}
          onClick={() => create(false)}
          className="mt-3 w-full rounded-xl border border-dashed border-slate-600 px-3 py-3 text-left text-slate-300 hover:bg-slate-800"
        >
          ➕ Add <span className="font-semibold">“{q.trim()}”</span> as a new exercise
        </button>
      )}
    </Sheet>
  )
}
