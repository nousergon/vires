import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  api,
  type ExerciseRecords,
  type RecordMetric,
  type RecordWindow,
} from '../lib/api'
import { useSettings } from '../lib/useSettings'
import { fmtClock } from '../lib/timer'
import { Button, Card, EmptyState, PageTitle, Spinner } from '../components/ui'
import SessionDetailSheet, { activityLine } from '../components/SessionDetailSheet'

type Tab = 'sessions' | 'records'

export default function HistoryPage() {
  const [tab, setTab] = useState<Tab>('sessions')
  return (
    <div>
      <PageTitle>History</PageTitle>
      <div className="mb-4 flex rounded-xl bg-slate-800 p-1 text-sm font-medium">
        {(['sessions', 'records'] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-1 rounded-lg py-1.5 capitalize transition ${
              tab === t ? 'bg-slate-700 text-amber-400' : 'text-slate-400'
            }`}
          >
            {t === 'records' ? '🏆 Records' : 'Sessions'}
          </button>
        ))}
      </div>
      {tab === 'sessions' ? <SessionsView /> : <RecordsView />}
    </div>
  )
}

// --------------------------------------------------------------------------- //
function SessionsView() {
  const qc = useQueryClient()
  const unit = useSettings().weight_unit
  const { data: workouts = [], isLoading } = useQuery({
    queryKey: ['workouts'],
    queryFn: api.listWorkouts,
  })
  const [detailId, setDetailId] = useState<number | null>(null)
  const [selecting, setSelecting] = useState(false)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [busy, setBusy] = useState(false)

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['workouts'] })
    qc.invalidateQueries({ queryKey: ['records'] })
    qc.invalidateQueries({ queryKey: ['calendar'] })
  }

  function exitSelect() {
    setSelecting(false)
    setSelected(new Set())
  }

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function deleteSelected() {
    if (selected.size === 0) return
    const n = selected.size
    if (!confirm(`Delete ${n} workout${n === 1 ? '' : 's'} from history? This can't be undone.`)) return
    setBusy(true)
    try {
      await Promise.all([...selected].map((id) => api.deleteWorkout(id)))
      exitSelect()
      refresh()
    } catch (e) {
      alert(`Couldn't delete: ${(e as Error).message.replace(/^\d+:\s*/, '')}`)
      refresh() // some may have deleted — resync the list
    } finally {
      setBusy(false)
    }
  }

  if (isLoading) return <Spinner />
  if (workouts.length === 0)
    return <EmptyState title="No workouts yet" hint="Your finished workouts show up here." />

  return (
    <>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs text-slate-500">
          {selecting ? `${selected.size} selected` : `${workouts.length} workouts`}
        </span>
        <button
          className="text-sm text-amber-300 hover:text-amber-200"
          onClick={() => (selecting ? exitSelect() : setSelecting(true))}
        >
          {selecting ? 'Cancel' : 'Select'}
        </button>
      </div>

      <div className={`space-y-2 ${selecting ? 'pb-20' : ''}`}>
        {workouts.map((w) => {
          const isSel = selected.has(w.id)
          const onClick = () => {
            if (selecting) toggle(w.id)
            else setDetailId(w.id)
          }
          return (
            <Card key={w.id} className={isSel ? 'ring-1 ring-amber-500' : ''}>
              <button className="flex w-full items-center gap-3 text-left" onClick={onClick}>
                {selecting && (
                  <span
                    className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-xs ${
                      isSel ? 'border-amber-500 bg-amber-500 text-slate-950' : 'border-slate-600 text-transparent'
                    }`}
                  >
                    ✓
                  </span>
                )}
                <span className="min-w-0 flex-1">
                  <span className="flex items-center justify-between">
                    <span className="truncate font-semibold text-slate-100">
                      {w.activity?.pack_weight_kg != null ? '🎒 ' : w.session_type === 'activity' ? '🏃 ' : ''}
                      {w.name || (w.session_type === 'activity' ? 'Activity' : 'Workout')}
                    </span>
                    <span className="ml-2 shrink-0 text-xs text-slate-400">
                      {new Date(w.started_at).toLocaleDateString()}
                    </span>
                  </span>
                  <span className="mt-1 block text-xs text-slate-400">
                    {w.session_type === 'activity' && w.activity ? (
                      activityLine(w.activity, unit)
                    ) : (
                      <>
                        {w.exercise_count} exercises · {w.set_count} sets
                        {w.total_volume > 0 && ` · ${w.total_volume.toLocaleString()} vol`}
                        {!w.ended_at && <span className="ml-2 text-amber-400">in progress</span>}
                      </>
                    )}
                  </span>
                </span>
              </button>
            </Card>
          )
        })}
      </div>

      {selecting && (
        <div className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-800 bg-slate-900/95 p-3 safe-bottom backdrop-blur">
          <div className="mx-auto flex max-w-md gap-2">
            <Button
              variant="danger"
              className="flex-1"
              onClick={deleteSelected}
              disabled={busy || selected.size === 0}
            >
              {busy ? 'Deleting…' : `Delete ${selected.size || ''}`.trim()}
            </Button>
            <Button variant="secondary" onClick={exitSelect} disabled={busy}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      <SessionDetailSheet sessionId={detailId} onClose={() => setDetailId(null)} />
    </>
  )
}

// --------------------------------------------------------------------------- //
const WINDOWS: { key: RecordWindow; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'year', label: 'Year' },
  { key: 'quarter', label: 'Quarter' },
  { key: 'month', label: 'Month' },
]

function RecordsView() {
  const [win, setWin] = useState<RecordWindow>('all')
  const unit = useSettings().weight_unit
  const { data: records = [], isLoading } = useQuery({
    queryKey: ['records', win],
    queryFn: () => api.records(win),
  })

  return (
    <div>
      <div className="mb-4 flex gap-1.5">
        {WINDOWS.map((w) => (
          <button
            key={w.key}
            onClick={() => setWin(w.key)}
            className={`flex-1 rounded-lg border py-1.5 text-xs font-medium ${
              win === w.key
                ? 'border-amber-500 bg-amber-500/10 text-amber-300'
                : 'border-slate-700 text-slate-400'
            }`}
          >
            {w.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <Spinner />
      ) : records.length === 0 ? (
        <EmptyState
          title="No records yet"
          hint={
            win === 'all'
              ? 'Log some sets and your bests appear here.'
              : 'No performed sets in this window.'
          }
        />
      ) : (
        <div className="space-y-2">
          {records.map((r) => (
            <RecordCard key={r.exercise.id} r={r} unit={unit} />
          ))}
        </div>
      )}
    </div>
  )
}

function RecordCard({ r, unit }: { r: ExerciseRecords; unit: string }) {
  return (
    <Card>
      <h3 className="mb-2 font-semibold text-slate-100">{r.exercise.name}</h3>
      {r.is_timed ? (
        <Metric label="Longest hold" m={r.longest_hold} fmt={(v) => fmtClock(Math.round(v))} highlight />
      ) : (
        <div className="grid grid-cols-2 gap-3">
          <Metric label="Est. 1RM" m={r.est_1rm} fmt={(v) => `${v} ${unit}`} highlight />
          <Metric label="Heaviest" m={r.heaviest} fmt={(v) => `${v} ${unit}`} />
          <Metric label="Best set volume" m={r.best_set_volume} fmt={(v) => v.toLocaleString()} />
          <Metric label="Most reps" m={r.most_reps} fmt={(v) => `${v}`} />
        </div>
      )}
    </Card>
  )
}

function Metric({
  label,
  m,
  fmt,
  highlight,
}: {
  label: string
  m: RecordMetric | null
  fmt: (v: number) => string
  highlight?: boolean
}) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
      {m ? (
        <>
          <div className={`font-bold ${highlight ? 'text-lg text-amber-300' : 'text-slate-100'}`}>
            {fmt(m.value)}
          </div>
          <div className="text-[11px] text-slate-500">
            {m.weight != null && m.reps != null && `${m.weight}×${m.reps} · `}
            {new Date(m.date).toLocaleDateString()}
          </div>
        </>
      ) : (
        <div className="text-slate-600">—</div>
      )}
    </div>
  )
}
