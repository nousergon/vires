import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type AilmentEpisode } from '../lib/api'
import { Button } from './ui'
import { isoDate } from '../lib/calendar'

function severityLabel(n: number): string {
  if (n <= 1) return 'minimal'
  if (n <= 3) return 'mild'
  if (n <= 5) return 'moderate'
  if (n <= 7) return 'significant'
  return 'severe'
}

/** Date-anchored injury episodes with daily severity check-ins. */
export default function AilmentsPanel({ onChanged }: { onChanged?: () => void }) {
  const qc = useQueryClient()
  const { data: ailments = [], isLoading } = useQuery({
    queryKey: ['ailments', 'open'],
    queryFn: () => api.listAilments('open'),
  })
  const [adding, setAdding] = useState(false)
  const [label, setLabel] = useState('')
  const [notes, setNotes] = useState('')
  const [severity, setSeverity] = useState('3')
  const [busy, setBusy] = useState(false)

  function refresh() {
    qc.invalidateQueries({ queryKey: ['ailments'] })
    qc.invalidateQueries({ queryKey: ['ailments-pending'] })
    onChanged?.()
  }

  async function register() {
    if (!label.trim()) return
    setBusy(true)
    try {
      await api.createAilment({
        label: label.trim(),
        onset_date: isoDate(new Date()),
        notes: notes.trim() || null,
        initial_severity: severity === '' ? null : Number(severity),
      })
      setLabel('')
      setNotes('')
      setSeverity('3')
      setAdding(false)
      refresh()
    } finally {
      setBusy(false)
    }
  }

  async function checkIn(ep: AilmentEpisode, sev: number, note?: string) {
    setBusy(true)
    try {
      await api.addAilmentCheckIn(ep.id, { severity: sev, note: note || null })
      refresh()
    } finally {
      setBusy(false)
    }
  }

  async function resolve(id: number) {
    setBusy(true)
    try {
      await api.updateAilment(id, { status: 'resolved' })
      refresh()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">Ailments</h2>
        {!adding && (
          <button className="text-sm text-amber-300 hover:text-amber-200" onClick={() => setAdding(true)}>
            + Register
          </button>
        )}
      </div>
      <p className="mb-2 text-xs text-slate-500">
        Acute or changing injuries — log severity today; the coach reads your trend before
        prescribing. A severity of 6+ (or a big jump between check-ins) may prompt the coach to
        suggest a plan refresh, and a severe lower-body/knee flare-up can warn or pause today's
        session before you start it.
      </p>

      {isLoading ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : ailments.length === 0 && !adding ? (
        <p className="text-sm text-slate-500">No active ailments.</p>
      ) : (
        <div className="space-y-2">
          {ailments.map((a) => (
            <AilmentCard
              key={a.id}
              ailment={a}
              busy={busy}
              onCheckIn={checkIn}
              onResolve={() => resolve(a.id)}
            />
          ))}
        </div>
      )}

      {adding && (
        <div className="mt-2 space-y-2 rounded-lg border border-rose-800/40 bg-rose-900/10 p-3">
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="e.g. Right knee"
            className="input"
          />
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            placeholder="What happened, what provokes it (optional)"
            className="input"
          />
          <label className="block text-xs text-slate-400">
            Severity today (0–10)
            <input
              type="number"
              min={0}
              max={10}
              value={severity}
              onChange={(e) => setSeverity(e.target.value)}
              className="input mt-1"
            />
          </label>
          <div className="flex gap-2">
            <Button className="flex-1" onClick={register} disabled={busy || !label.trim()}>
              {busy ? 'Saving…' : 'Register ailment'}
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

function AilmentCard({
  ailment: a,
  busy,
  onCheckIn,
  onResolve,
}: {
  ailment: AilmentEpisode
  busy: boolean
  onCheckIn: (a: AilmentEpisode, sev: number, note?: string) => void
  onResolve: () => void
}) {
  const [sev, setSev] = useState(String(a.latest_severity ?? 3))
  const [note, setNote] = useState('')

  return (
    <div className="rounded-xl border border-rose-800/40 bg-rose-900/10 p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-semibold text-rose-100">{a.label}</div>
          <div className="text-xs text-rose-200/70">
            since {a.onset_date}
            {a.latest_severity != null && (
              <>
                {' '}
                · latest {a.latest_severity}/10 ({severityLabel(a.latest_severity)})
                {a.latest_check_in_date && ` on ${a.latest_check_in_date}`}
              </>
            )}
          </div>
          {a.notes && <p className="mt-1 text-xs text-slate-400">{a.notes}</p>}
        </div>
        <span className="shrink-0 rounded bg-rose-500/20 px-1.5 py-0.5 text-[10px] uppercase text-rose-300">
          {a.status}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap items-end gap-2 border-t border-rose-900/40 pt-2">
        <label className="text-xs text-slate-400">
          Today
          <input
            type="number"
            min={0}
            max={10}
            value={sev}
            onChange={(e) => setSev(e.target.value)}
            className="input mt-0.5 w-16"
          />
        </label>
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Note (optional)"
          className="input min-w-0 flex-1 text-sm"
        />
        <Button
          variant="secondary"
          disabled={busy || sev === ''}
          onClick={() => onCheckIn(a, Number(sev), note.trim() || undefined)}
        >
          Check in
        </Button>
        <button
          className="text-xs text-slate-500 hover:text-emerald-400"
          disabled={busy}
          onClick={onResolve}
        >
          Resolved ✓
        </button>
      </div>
    </div>
  )
}

/** Inline check-in rows for the pre-workout gate. */
export function AilmentCheckInForm({
  pending,
  onDone,
  onCancel,
}: {
  pending: { ailment: AilmentEpisode; last_severity: number | null }[]
  onDone: () => void
  onCancel: () => void
}) {
  const [values, setValues] = useState<Record<number, string>>(() =>
    Object.fromEntries(pending.map((p) => [p.ailment.id, String(p.last_severity ?? 3)])),
  )
  const [busy, setBusy] = useState(false)

  async function submit() {
    setBusy(true)
    try {
      for (const p of pending) {
        const raw = values[p.ailment.id]
        if (raw === '') continue
        await api.addAilmentCheckIn(p.ailment.id, { severity: Number(raw) })
      }
      onDone()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-300">
        Quick check-in before training — how are your active ailments today (0–10)?
      </p>
      {pending.map((p) => (
        <label key={p.ailment.id} className="flex items-center justify-between gap-3 text-sm">
          <span className="text-slate-200">{p.ailment.label}</span>
          <input
            type="number"
            min={0}
            max={10}
            className="input w-16"
            value={values[p.ailment.id] ?? ''}
            onChange={(e) => setValues((v) => ({ ...v, [p.ailment.id]: e.target.value }))}
          />
        </label>
      ))}
      <div className="flex gap-2">
        <Button className="flex-1" onClick={submit} disabled={busy}>
          {busy ? 'Saving…' : 'Continue to workout'}
        </Button>
        <Button variant="secondary" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </div>
  )
}
