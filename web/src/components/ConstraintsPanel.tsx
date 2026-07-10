import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api, type Constraint } from '../lib/api'
import { Button } from './ui'

const CONSTRAINT_KINDS = ['injury', 'schedule', 'equipment'] as const
type ConstraintKind = (typeof CONSTRAINT_KINDS)[number]

const DISC_DIRECTIVES =
  'avoid heavy axial spinal loading; bias toward deep-stabilizer / anti-rotation / ' +
  'anti-lateral-flexion trunk work and controlled eccentric (descent) work; defer rehab to PT'

/** User-global training bounds (schedule, equipment, chronic injuries). */
export default function ConstraintsPanel({
  constraints,
  onChanged,
  compact = false,
}: {
  constraints: Constraint[]
  onChanged: () => void
  compact?: boolean
}) {
  const qc = useQueryClient()
  const [adding, setAdding] = useState(false)
  const [kind, setKind] = useState<ConstraintKind>('injury')
  const [label, setLabel] = useState('')
  const [directives, setDirectives] = useState('')
  const [busy, setBusy] = useState(false)

  function refresh() {
    qc.invalidateQueries({ queryKey: ['active-objective'] })
    onChanged()
  }

  async function add() {
    if (!label.trim()) return
    setBusy(true)
    try {
      await api.createConstraint({
        kind,
        label: label.trim(),
        directives: directives.trim() || null,
      })
      setLabel('')
      setDirectives('')
      setAdding(false)
      refresh()
    } finally {
      setBusy(false)
    }
  }

  async function remove(id: number) {
    setBusy(true)
    try {
      await api.deleteConstraint(id)
      refresh()
    } finally {
      setBusy(false)
    }
  }

  function onLabelBlur() {
    if (kind === 'injury' && !directives && /disc|l[1-5]-?l[1-5]|lumbar/i.test(label)) {
      setDirectives(DISC_DIRECTIVES)
    }
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          {compact ? 'Constraints' : 'Training constraints'}
        </h2>
        {!adding && (
          <button className="text-sm text-amber-300 hover:text-amber-200" onClick={() => setAdding(true)}>
            + Add
          </button>
        )}
      </div>
      {!compact && (
        <p className="mb-2 text-xs text-slate-500">
          Standing rules the coach honors on every plan — schedule, equipment, chronic bounds. For
          acute injuries with changing severity, use <strong className="font-medium text-slate-400">Ailments</strong>{' '}
          below.
        </p>
      )}

      {constraints.length === 0 && !adding && (
        <p className="text-sm text-slate-500">None — the coach trains with no restrictions.</p>
      )}

      <div className="space-y-2">
        {constraints.map((c) => (
          <div
            key={c.id}
            className="flex items-start justify-between gap-2 rounded-lg border border-slate-800 bg-slate-800/40 px-3 py-2"
          >
            <div className="min-w-0">
              <div className="text-sm font-medium text-slate-100">
                {c.label}
                <span className="ml-2 text-xs text-slate-500">{c.kind}</span>
                {c.defer_to_professional && (
                  <span className="ml-1 text-xs text-slate-500">· defer to PT</span>
                )}
              </div>
              {c.directives && <div className="mt-0.5 text-xs text-slate-400">{c.directives}</div>}
            </div>
            <button
              className="shrink-0 text-slate-600 hover:text-red-400"
              onClick={() => remove(c.id)}
              disabled={busy}
              aria-label="Remove constraint"
            >
              ✕
            </button>
          </div>
        ))}
      </div>

      {adding && (
        <div className="mt-2 space-y-2 rounded-lg border border-slate-800 bg-slate-800/40 p-3">
          <div className="flex gap-2">
            {CONSTRAINT_KINDS.map((k) => (
              <button
                key={k}
                onClick={() => setKind(k)}
                className={`flex-1 rounded-lg border px-2 py-1.5 text-xs ${
                  kind === k
                    ? 'border-amber-500 bg-amber-500/10 text-amber-200'
                    : 'border-slate-700 text-slate-300 hover:bg-slate-800'
                }`}
              >
                {k}
              </button>
            ))}
          </div>
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            onBlur={onLabelBlur}
            placeholder="e.g. lift 2× week, recovering L4-L5 disc"
            className="input"
          />
          <textarea
            value={directives}
            onChange={(e) => setDirectives(e.target.value)}
            rows={3}
            placeholder="What to avoid / bias toward (the coach trains around this)."
            className="input"
          />
          <div className="flex gap-2">
            <Button className="flex-1" onClick={add} disabled={busy || !label.trim()}>
              {busy ? 'Adding…' : 'Add constraint'}
            </Button>
            <Button variant="secondary" onClick={() => setAdding(false)} disabled={busy}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
