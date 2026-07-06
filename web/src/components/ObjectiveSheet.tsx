import { type ReactNode, useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type Objective } from '../lib/api'
import ConstraintsPanel from './ConstraintsPanel'
import { Button, Sheet, Spinner } from './ui'

/**
 * Create a new objective or edit an existing one (by ``objectiveId``), plus the
 * user's global training constraints. A user may hold any number of concurrent
 * objectives; the coach derives a *focus* across them (manual ``is_primary`` pin
 * → next dated peak → standing goal) and periodizes a season toward it. Saving
 * with no ``objectiveId`` always POSTs a NEW objective.
 */
export default function ObjectiveSheet({
  open,
  objectiveId,
  defaultDate,
  defaultKind,
  onClose,
  onSaved,
}: {
  open: boolean
  // The objective to edit; omit / null to create a brand-new one.
  objectiveId?: number | null
  // Seed target_date for a new dated objective (e.g. the tapped calendar day).
  defaultDate?: string | null
  // Seed the Type toggle for a new objective (e.g. 'open_ended' from the
  // Status tab's general-objectives list, which has no date to anchor to).
  defaultKind?: 'dated' | 'open_ended'
  onClose: () => void
  onSaved: () => void
}) {
  const qc = useQueryClient()
  // All objectives — used to seed the edited row + derive its milestones (so the
  // milestones editor works for ANY objective, not just the derived focus).
  const { data: all = [], isLoading: loadingObjectives } = useQuery({
    queryKey: ['objectives'],
    queryFn: api.listObjectives,
    enabled: open,
  })
  // Constraints are user-global (bounds on every objective) — fetched separately.
  const { data: active, isLoading: loadingActive } = useQuery({
    queryKey: ['active-objective'],
    queryFn: api.activeObjective,
    enabled: open,
  })
  const isLoading = loadingObjectives || loadingActive

  const editing = objectiveId != null ? (all.find((o) => o.id === objectiveId) ?? null) : null
  const milestones = objectiveId != null ? all.filter((o) => o.parent_objective_id === objectiveId) : []
  const isSub = editing?.parent_objective_id != null

  const [name, setName] = useState('')
  const [kind, setKind] = useState<'dated' | 'open_ended'>('dated')
  const [targetDate, setTargetDate] = useState('')
  const [eventEndDate, setEventEndDate] = useState('')
  const [sport, setSport] = useState('alpine')
  const [priority, setPriority] = useState(0)
  const [isPrimary, setIsPrimary] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Seed the form when the sheet opens / the edited objective changes.
  useEffect(() => {
    if (!open) return
    setError(null)
    setName(editing?.name ?? '')
    setKind(editing?.kind ?? defaultKind ?? 'dated')
    setTargetDate(editing?.target_date ?? defaultDate ?? '')
    setEventEndDate(editing?.event_end_date ?? '')
    setSport(editing?.sport ?? 'alpine')
    setPriority(editing?.priority ?? 0)
    setIsPrimary(editing?.is_primary ?? false)
  }, [open, editing?.id, defaultDate, defaultKind]) // eslint-disable-line react-hooks/exhaustive-deps

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['active-objective'] })
    qc.invalidateQueries({ queryKey: ['objectives'] })
  }

  const saveObjective = useMutation({
    mutationFn: async () => {
      const body = {
        name: name.trim(),
        kind,
        target_date: kind === 'dated' ? targetDate || null : null,
        event_end_date: kind === 'dated' && eventEndDate ? eventEndDate : null,
        sport: sport.trim() || null,
        priority,
        // A sub-objective can never be the focus; never send is_primary for one.
        ...(isSub ? {} : { is_primary: isPrimary }),
      }
      return editing ? api.updateObjective(editing.id, body) : api.createObjective(body)
    },
    onSuccess: () => {
      refresh()
      onSaved()
    },
    onError: (e) => setError((e as Error).message.replace(/^\d+:\s*/, '')),
  })

  const dateMissing = kind === 'dated' && !targetDate
  const eventEndInvalid = !!eventEndDate && !!targetDate && eventEndDate < targetDate
  const canSave = !!name.trim() && !dateMissing && !eventEndInvalid && !saveObjective.isPending

  return (
    <Sheet open={open} onClose={onClose} title={editing ? '🎯 Edit objective' : '🎯 New objective'}>
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
              <>
                <Field label="Target date" hint="the day you peak / taper to">
                  <input
                    type="date"
                    value={targetDate}
                    onChange={(e) => setTargetDate(e.target.value)}
                    className="input"
                  />
                </Field>

                <Field
                  label="Event ends"
                  hint="optional — last day of a multi-day event (no training during it)"
                >
                  <input
                    type="date"
                    value={eventEndDate}
                    min={targetDate || undefined}
                    onChange={(e) => setEventEndDate(e.target.value)}
                    className="input"
                  />
                </Field>
              </>
            )}

            <Field label="Sport" hint="drives the needs-analysis (alpine is authored)">
              <input
                value={sport}
                onChange={(e) => setSport(e.target.value)}
                placeholder="alpine"
                className="input"
              />
            </Field>

            <Field label="Priority" hint="rank among concurrent objectives (higher = more important)">
              <input
                type="number"
                value={priority}
                onChange={(e) => setPriority(Number(e.target.value) || 0)}
                className="input"
              />
            </Field>

            {!isSub && (
              <label className="flex items-center gap-2 text-sm text-slate-300">
                <input
                  type="checkbox"
                  checked={isPrimary}
                  onChange={(e) => setIsPrimary(e.target.checked)}
                  className="h-4 w-4 accent-amber-500"
                />
                Pin as my focus (override the auto-derived next peak)
              </label>
            )}

            {error && (
              <p className="rounded-lg border border-red-800/50 bg-red-900/20 px-3 py-2 text-sm text-red-300">
                {error}
              </p>
            )}

            <Button className="w-full" onClick={() => saveObjective.mutate()} disabled={!canSave}>
              {saveObjective.isPending
                ? 'Saving…'
                : editing
                  ? 'Update objective'
                  : 'Add objective'}
            </Button>
          </div>

          {editing && editing.kind === 'dated' && !isSub && (
            <MilestonesEditor parent={editing} milestones={milestones} onChanged={refresh} />
          )}

          <div className="border-t border-slate-800 pt-4">
            <ConstraintsPanel constraints={active?.constraints ?? []} onChanged={refresh} compact />
          </div>

          <p className="text-xs text-slate-500">
            The coach reverse-builds a periodized plan toward your focus objective and trains around
            your constraints. It never prescribes treatment for an injury — defer that to your
            PT/physician.
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
