import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type CalendarEntry } from '../lib/api'
import { Button, EmptyState, PageTitle, Sheet, Spinner } from '../components/ui'
import CoachSheet from '../components/CoachSheet'
import { ACTIVE_KEY } from './WorkoutPage'
import {
  addMonths,
  isoDate,
  MONTH_LABELS,
  monthMatrix,
  sameDay,
  WEEKDAY_LABELS,
} from '../lib/calendar'

export default function PlanPage() {
  const qc = useQueryClient()
  const nav = useNavigate()
  const today = new Date()
  const [month, setMonth] = useState(() => new Date(today.getFullYear(), today.getMonth(), 1))
  const [selected, setSelected] = useState<Date | null>(null)
  const [coachOpen, setCoachOpen] = useState(false)

  const weeks = useMemo(() => monthMatrix(month.getFullYear(), month.getMonth()), [month])
  const rangeStart = isoDate(weeks[0][0])
  const rangeEnd = isoDate(weeks[weeks.length - 1][6])

  const { data: entries = [], isLoading } = useQuery({
    queryKey: ['calendar', rangeStart, rangeEnd],
    queryFn: () => api.calendar(rangeStart, rangeEnd),
  })

  const byDate = useMemo(() => {
    const m = new Map<string, CalendarEntry[]>()
    entries.forEach((e) => m.set(e.date, [...(m.get(e.date) ?? []), e]))
    return m
  }, [entries])

  const refresh = () => qc.invalidateQueries({ queryKey: ['calendar'] })

  function onStarted(sessionId: number) {
    localStorage.setItem(ACTIVE_KEY, String(sessionId))
    nav('/train')
  }

  return (
    <div>
      <PageTitle right={<Button onClick={() => setCoachOpen(true)}>✨ Coach</Button>}>Plan</PageTitle>

      <div className="mb-3 flex items-center justify-between">
        <button className="px-2 py-1 text-slate-400" onClick={() => setMonth(addMonths(month, -1))}>
          ‹
        </button>
        <button
          className="text-base font-semibold text-slate-100"
          onClick={() => setMonth(new Date(today.getFullYear(), today.getMonth(), 1))}
        >
          {MONTH_LABELS[month.getMonth()]} {month.getFullYear()}
        </button>
        <button className="px-2 py-1 text-slate-400" onClick={() => setMonth(addMonths(month, 1))}>
          ›
        </button>
      </div>

      {isLoading ? (
        <Spinner />
      ) : (
        <CalendarGrid weeks={weeks} month={month} today={today} byDate={byDate} onPick={setSelected} />
      )}

      <Legend />

      <DaySheet
        date={selected}
        entries={selected ? byDate.get(isoDate(selected)) ?? [] : []}
        onClose={() => setSelected(null)}
        onChanged={refresh}
        onStarted={onStarted}
      />
      <CoachSheet open={coachOpen} onClose={() => setCoachOpen(false)} onSaved={refresh} />
    </div>
  )
}

// --------------------------------------------------------------------------- //
function Dot({ className }: { className: string }) {
  return <span className={`h-1.5 w-1.5 rounded-full ${className}`} />
}

function CalendarGrid({
  weeks,
  month,
  today,
  byDate,
  onPick,
}: {
  weeks: Date[][]
  month: Date
  today: Date
  byDate: Map<string, CalendarEntry[]>
  onPick: (d: Date) => void
}) {
  return (
    <div className="select-none">
      <div className="mb-1 grid grid-cols-7 text-center text-[10px] uppercase text-slate-500">
        {WEEKDAY_LABELS.map((l) => (
          <div key={l}>{l}</div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {weeks.flat().map((d, i) => {
          const inMonth = d.getMonth() === month.getMonth()
          const es = byDate.get(isoDate(d)) ?? []
          const planned = es.some((e) => e.kind === 'planned' && e.status === 'planned')
          const done = es.some(
            (e) =>
              (e.kind === 'session' && e.status === 'completed') ||
              (e.kind === 'planned' && e.status === 'completed'),
          )
          const active = es.some((e) => e.kind === 'session' && e.status === 'in_progress')
          const isToday = sameDay(d, today)
          return (
            <button
              key={i}
              onClick={() => onPick(d)}
              className={`flex aspect-square flex-col items-center justify-center rounded-lg text-sm ${
                inMonth ? 'text-slate-200' : 'text-slate-600'
              } ${isToday ? 'ring-1 ring-amber-500' : ''} ${
                es.length ? 'bg-slate-800/60' : 'hover:bg-slate-800/40'
              }`}
            >
              <span>{d.getDate()}</span>
              <span className="mt-0.5 flex h-1.5 gap-0.5">
                {planned && <Dot className="bg-amber-400" />}
                {done && <Dot className="bg-emerald-400" />}
                {active && <Dot className="bg-amber-400 animate-pulse" />}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

function Legend() {
  return (
    <div className="mt-3 flex justify-center gap-4 text-[11px] text-slate-500">
      <span className="flex items-center gap-1">
        <Dot className="bg-amber-400" /> planned
      </span>
      <span className="flex items-center gap-1">
        <Dot className="bg-emerald-400" /> completed
      </span>
    </div>
  )
}

// --------------------------------------------------------------------------- //
function DaySheet({
  date,
  entries,
  onClose,
  onChanged,
  onStarted,
}: {
  date: Date | null
  entries: CalendarEntry[]
  onClose: () => void
  onChanged: () => void
  onStarted: (sessionId: number) => void
}) {
  const { data: templates = [] } = useQuery({ queryKey: ['templates'], queryFn: api.listTemplates })
  const [busy, setBusy] = useState(false)
  const title = date
    ? date.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })
    : ''

  async function start(plannedId: number) {
    setBusy(true)
    try {
      const ws = await api.startPlanned(plannedId)
      onStarted(ws.id)
    } finally {
      setBusy(false)
    }
  }

  async function remove(plannedId: number) {
    setBusy(true)
    try {
      await api.deletePlanned(plannedId)
      onChanged()
    } finally {
      setBusy(false)
    }
  }

  async function schedule(templateId: number) {
    if (!date) return
    setBusy(true)
    try {
      await api.createPlanned({ scheduled_date: isoDate(date), template_id: templateId })
      onChanged()
    } finally {
      setBusy(false)
    }
  }

  const planned = entries.filter((e) => e.kind === 'planned')
  const sessions = entries.filter((e) => e.kind === 'session')

  return (
    <Sheet open={!!date} onClose={onClose} title={title}>
      <div className="space-y-4">
        {entries.length === 0 && <EmptyState title="Nothing scheduled" hint="Schedule a routine below or ask the Coach." />}

        {planned.map((e) => (
          <div key={`p${e.id}`} className="rounded-xl border border-slate-800 bg-slate-800/40 p-3">
            <div className="flex items-center justify-between">
              <div>
                <div className="font-semibold text-slate-100">{e.name || 'Workout'}</div>
                <div className="text-xs text-slate-400">
                  {e.exercise_count} exercises · {e.status}
                </div>
              </div>
              <button
                className="text-slate-600 hover:text-red-400"
                onClick={() => remove(e.id)}
                disabled={busy}
                aria-label="Delete"
              >
                ✕
              </button>
            </div>
            {e.status !== 'completed' ? (
              <Button className="mt-2 w-full" onClick={() => start(e.id)} disabled={busy}>
                Start workout
              </Button>
            ) : (
              <p className="mt-2 text-xs text-emerald-400">Completed ✓</p>
            )}
          </div>
        ))}

        {sessions.map((e) => (
          <div key={`s${e.id}`} className="rounded-xl border border-slate-800 bg-slate-800/40 p-3">
            <div className="font-semibold text-slate-100">{e.name || 'Workout'}</div>
            <div className="text-xs text-slate-400">
              {e.exercise_count} exercises ·{' '}
              {e.status === 'completed' ? (
                <span className="text-emerald-400">logged</span>
              ) : (
                <span className="text-amber-400">in progress</span>
              )}
            </div>
          </div>
        ))}

        {templates.length > 0 && (
          <div className="border-t border-slate-800 pt-3">
            <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Schedule a routine here
            </p>
            <div className="flex flex-wrap gap-2">
              {templates.map((t) => (
                <button
                  key={t.id}
                  onClick={() => schedule(t.id)}
                  disabled={busy}
                  className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-40"
                >
                  + {t.name}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </Sheet>
  )
}
