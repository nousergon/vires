import { type ReactNode, useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type Constraint, type Objective } from '../lib/api'
import { Button, Sheet, Spinner } from './ui'

const CONSTRAINT_KINDS = ['injury', 'schedule', 'equipment'] as const
type ConstraintKind = (typeof CONSTRAINT_KINDS)[number]

const DISC_DIRECTIVES =
  'avoid heavy axial spinal loading; bias toward deep-stabilizer / anti-rotation / ' +
  'anti-lateral-flexion trunk work and controlled eccentric (descent) work; defer rehab to PT'

/**
 * Create/edit the single active *primary* objective + its constraints, directly
 * in the app (no CLI). The coach reverse-builds a plan toward this objective and
 * trains around the constraints. One primary per user — saving creates it or
 * updates the existing one.
 */
export default function ObjectiveSheet({
  open,
  onClose,
  onSaved,
}: {
  open: boolean
  onClose: () => void
  onSaved: () => void
}) {
  const qc = useQueryClient()
  const { data: active, isLoading } = useQuery({
    queryKey: ['active-objective'],
    queryFn: api.activeObjective,
    enabled: open,
  })
  const objective = active?.objective ?? null

  const [name, setName] = useState('')
  const [kind, setKind] = useState<'dated' | 'open_ended'>('dated')
  const [targetDate, setTargetDate] = useState('')
  const [sport, setSport] = useState('alpine')
  const [error, setError] = useState<string | null>(null)

  // Seed the form when the sheet opens / the loaded objective changes.
  useEffect(() => {
    if (!open) return
    setError(null)
    setName(objective?.name ?? '')
    setKind(objective?.kind ?? 'dated')
    setTargetDate(objective?.target_date ?? '')
    setSport(objective?.sport ?? 'alpine')
  }, [open, objective?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const refresh = () => qc.invalidateQueries({ queryKey: ['active-objective'] })

  const saveObjective = useMutation({
    mutationFn: async () => {
      const body = {
        name: name.trim(),
        kind,
        target_date: kind === 'dated' ? targetDate || null : null,
        sport: sport.trim() || null,
        is_primary: true,
      }
      return objective
        ? api.updateObjective(objective.id, body)
        : api.createObjective(body)
    },
    onSuccess: () => {
      refresh()
      onSaved()
    },
    onError: (e) => setError((e as Error).message.replace(/^\d+:\s*/, '')),
  })

  const dateMissing = kind === 'dated' && !targetDate
  const canSave = !!name.trim() && !dateMissing && !saveObjective.isPending

  return (
    <Sheet open={open} onClose={onClose} title="🎯 Objective">
      {isLoading ? (
        <Spinner />
      ) : (
        <div className="space-y-5">
          <div className="space-y-3">
            <Field label="Objective">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Climb Baker"
                className="input"
              />
            </Field>

            <Field label="Type">
              <div className="flex gap-2">
                {(['dated', 'open_ended'] as const).map((k) => (
                  <button
                    key={k}
                    onClick={() => setKind(k)}
                    className={`flex-1 rounded-lg border px-3 py-2 text-sm ${
                      kind === k
                        ? 'border-amber-500 bg-amber-500/10 text-amber-200'
                        : 'border-slate-700 text-slate-300 hover:bg-slate-800'
                    }`}
                  >
                    {k === 'dated' ? 'Has a date' : 'Open-ended'}
                  </button>
                ))}
              </div>
            </Field>

            {kind === 'dated' && (
              <Field label="Target date" hint="the day you peak / taper to">
                <input
                  type="date"
                  value={targetDate}
                  onChange={(e) => setTargetDate(e.target.value)}
                  className="input"
                />
              </Field>
            )}

            <Field label="Sport" hint="drives the needs-analysis (alpine is authored)">
              <input
                value={sport}
                onChange={(e) => setSport(e.target.value)}
                placeholder="alpine"
                className="input"
              />
            </Field>

            {error && (
              <p className="rounded-lg border border-red-800/50 bg-red-900/20 px-3 py-2 text-sm text-red-300">
                {error}
              </p>
            )}

            <Button className="w-full" onClick={() => saveObjective.mutate()} disabled={!canSave}>
              {saveObjective.isPending ? 'Saving…' : objective ? 'Update objective' : 'Set objective'}
            </Button>
          </div>

          {objective && objective.kind === 'dated' && (
            <MilestonesEditor
              parent={objective}
              milestones={active?.milestones ?? []}
              onChanged={refresh}
            />
          )}

          <ConstraintsEditor constraints={active?.constraints ?? []} onChanged={refresh} />

          <p className="text-xs text-slate-500">
            The coach reverse-builds a periodized plan toward this objective and trains around your
            constraints. It never prescribes treatment for an injury — defer that to your PT/physician.
          </p>
        </div>
      )}
    </Sheet>
  )
}

// --------------------------------------------------------------------------- //
/**
 * Training milestones (sub-objectives) nested under the active objective. A
 * milestone — e.g. a "Mailbox Peak" training hike under "Climb Baker" — is a
 * dated benchmark the coach periodizes a mini-taper/retest around; it does NOT
 * become the focus and never hijacks the parent's plan. It must fall on or
 * before the parent's target date (the server enforces this).
 */
function MilestonesEditor({
  parent,
  milestones,
  onChanged,
}: {
  parent: Objective
  milestones: Objective[]
  onChanged: () => void
}) {
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')
  const [date, setDate] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function add() {
    if (!name.trim() || !date) return
    setBusy(true)
    setError(null)
    try {
      await api.createObjective({
        name: name.trim(),
        kind: 'dated',
        target_date: date,
        sport: parent.sport, // inherit the parent's needs-analysis by default
        is_primary: false,
        parent_objective_id: parent.id,
      })
      setName('')
      setDate('')
      setAdding(false)
      onChanged()
    } catch (e) {
      setError((e as Error).message.replace(/^\d+:\s*/, ''))
    } finally {
      setBusy(false)
    }
  }

  async function remove(id: number) {
    setBusy(true)
    try {
      await api.deleteObjective(id)
      onChanged()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="border-t border-slate-800 pt-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          Training milestones
        </h3>
        {!adding && (
          <button
            className="text-sm text-amber-300 hover:text-amber-200"
            onClick={() => setAdding(true)}
          >
            + Add
          </button>
        )}
      </div>

      {milestones.length === 0 && !adding && (
        <p className="text-sm text-slate-500">
          None — add a dated benchmark (e.g. a training hike) that counts toward this
          objective without becoming a goal of its own.
        </p>
      )}

      <div className="space-y-2">
        {milestones.map((m) => (
          <div
            key={m.id}
            className="flex items-start justify-between gap-2 rounded-lg border border-slate-800 bg-slate-800/40 px-3 py-2"
          >
            <div className="min-w-0">
              <div className="text-sm font-medium text-slate-100">{m.name}</div>
              {m.target_date && (
                <div className="mt-0.5 text-xs text-slate-400">{m.target_date}</div>
              )}
            </div>
            <button
              className="shrink-0 text-slate-600 hover:text-red-400"
              onClick={() => remove(m.id)}
              disabled={busy}
              aria-label="Remove milestone"
            >
              ✕
            </button>
          </div>
        ))}
      </div>

      {adding && (
        <div className="mt-2 space-y-2 rounded-lg border border-slate-800 bg-slate-800/40 p-3">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Mailbox Peak (loaded-pack hike)"
            className="input"
          />
          <input
            type="date"
            value={date}
            max={parent.target_date ?? undefined}
            onChange={(e) => setDate(e.target.value)}
            className="input"
          />
          {error && (
            <p className="rounded-lg border border-red-800/50 bg-red-900/20 px-3 py-2 text-xs text-red-300">
              {error}
            </p>
          )}
          <div className="flex gap-2">
            <Button className="flex-1" onClick={add} disabled={busy || !name.trim() || !date}>
              {busy ? 'Adding…' : 'Add milestone'}
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setAdding(false)
                setError(null)
              }}
              disabled={busy}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

// --------------------------------------------------------------------------- //
function ConstraintsEditor({
  constraints,
  onChanged,
}: {
  constraints: Constraint[]
  onChanged: () => void
}) {
  const [adding, setAdding] = useState(false)
  const [kind, setKind] = useState<ConstraintKind>('injury')
  const [label, setLabel] = useState('')
  const [directives, setDirectives] = useState('')
  const [busy, setBusy] = useState(false)

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
      onChanged()
    } finally {
      setBusy(false)
    }
  }

  async function remove(id: number) {
    setBusy(true)
    try {
      await api.deleteConstraint(id)
      onChanged()
    } finally {
      setBusy(false)
    }
  }

  // Pre-fill the disc directives when the user names a lumbar/disc injury.
  function onLabelBlur() {
    if (kind === 'injury' && !directives && /disc|l[1-5]-?l[1-5]|lumbar/i.test(label)) {
      setDirectives(DISC_DIRECTIVES)
    }
  }

  return (
    <div className="border-t border-slate-800 pt-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400">Constraints</h3>
        {!adding && (
          <button className="text-sm text-amber-300 hover:text-amber-200" onClick={() => setAdding(true)}>
            + Add
          </button>
        )}
      </div>

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
                {c.defer_to_professional && <span className="ml-1 text-xs text-slate-500">· defer to PT</span>}
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
            placeholder="e.g. recovering L4-L5 disc"
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

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
        {hint && <span className="ml-2 normal-case font-normal text-slate-600">{hint}</span>}
      </span>
      {children}
    </label>
  )
}
