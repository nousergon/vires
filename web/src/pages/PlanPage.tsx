import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  api,
  type CalendarEntry,
  type CalendarEventOccurrence,
  type Objective,
  type PlannedExercise,
} from '../lib/api'
import { Button, EmptyState, PageTitle, Sheet, Spinner } from '../components/ui'
import CoachSheet from '../components/CoachSheet'
import ObjectiveSheet from '../components/ObjectiveSheet'
import CalendarEventSheet from '../components/CalendarEventSheet'
import ActivityForm from '../components/ActivityForm'
import { useSettings } from '../lib/useSettings'
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
  const [coachAutoStart, setCoachAutoStart] = useState(false)
  // { open } with an optional id — id present = edit that objective, absent = add
  // new (optionally seeded with the tapped day via `date`, dated objectives only).
  const [objectiveSheet, setObjectiveSheet] = useState<{ open: boolean; id?: number; date?: string }>({
    open: false,
  })
  // { open } with an optional id — id present = edit that calendar event, absent = add
  // new (optionally seeded with the tapped day via `date`).
  const [eventSheet, setEventSheet] = useState<{ open: boolean; id?: number; date?: string }>({
    open: false,
  })
  // Log-an-activity sheet, optionally seeded with the tapped calendar day.
  const [activitySheet, setActivitySheet] = useState<{ open: boolean; date?: string }>({
    open: false,
  })
  const [modifyProgram, setModifyProgram] = useState<{ id: number; name: string } | null>(null)

  const openObjective = (id?: number, date?: string) => setObjectiveSheet({ open: true, id, date })
  const openEvent = (id?: number, date?: string) => setEventSheet({ open: true, id, date })
  const openActivity = (date?: string) => setActivitySheet({ open: true, date })

  const openCoach = (auto: boolean) => {
    setCoachAutoStart(auto)
    setCoachOpen(true)
  }

  const weeks = useMemo(() => monthMatrix(month.getFullYear(), month.getMonth()), [month])
  const rangeStart = isoDate(weeks[0][0])
  const rangeEnd = isoDate(weeks[weeks.length - 1][6])

  const { data: entries = [], isLoading } = useQuery({
    queryKey: ['calendar', rangeStart, rangeEnd],
    queryFn: () => api.calendar(rangeStart, rangeEnd),
  })

  // Athletic-calendar events (markers) — separate endpoint from objectives
  // (bands); weekly recurrence is expanded server-side within [rangeStart, rangeEnd].
  const { data: occurrences = [] } = useQuery({
    queryKey: ['calendar-events-window', rangeStart, rangeEnd],
    queryFn: () => api.calendarEventsWindow(rangeStart, rangeEnd),
  })

  const byDate = useMemo(() => {
    const m = new Map<string, CalendarEntry[]>()
    entries.forEach((e) => m.set(e.date, [...(m.get(e.date) ?? []), e]))
    return m
  }, [entries])

  const eventsByDate = useMemo(() => {
    const m = new Map<string, CalendarEventOccurrence[]>()
    occurrences.forEach((o) =>
      m.set(o.occurrence_date, [...(m.get(o.occurrence_date) ?? []), o]),
    )
    return m
  }, [occurrences])

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['calendar'] })
    qc.invalidateQueries({ queryKey: ['calendar-events'] })
    qc.invalidateQueries({ queryKey: ['calendar-events-window'] })
    qc.invalidateQueries({ queryKey: ['programs'] })
    qc.invalidateQueries({ queryKey: ['active-objective'] })
  }

  function onStarted(sessionId: number) {
    localStorage.setItem(ACTIVE_KEY, String(sessionId))
    nav('/train')
  }

  return (
    <div>
      <PageTitle right={<Button onClick={() => openCoach(false)}>✨ Coach</Button>}>Plan</PageTitle>

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
        <CalendarGrid
          weeks={weeks}
          month={month}
          today={today}
          byDate={byDate}
          eventsByDate={eventsByDate}
          onPick={setSelected}
        />
      )}

      <Legend />

      <ObjectiveSection
        onEdit={openObjective}
        onGenerate={() => openCoach(true)}
      />

      <EventsSection onAdd={() => openEvent()} />

      <ProgramsSection onModify={setModifyProgram} onChanged={refresh} />

      <DaySheet
        date={selected}
        entries={selected ? byDate.get(isoDate(selected)) ?? [] : []}
        occurrences={selected ? eventsByDate.get(isoDate(selected)) ?? [] : []}
        onClose={() => setSelected(null)}
        onChanged={refresh}
        onStarted={onStarted}
        onEditEvent={(id) => openEvent(id)}
        onAddEvent={() => (selected ? openEvent(undefined, isoDate(selected)) : openEvent())}
        onAddActivity={() => (selected ? openActivity(isoDate(selected)) : openActivity())}
        onAddObjective={() => (selected ? openObjective(undefined, isoDate(selected)) : openObjective())}
      />
      <ObjectiveSheet
        open={objectiveSheet.open}
        objectiveId={objectiveSheet.id}
        defaultDate={objectiveSheet.date}
        onClose={() => setObjectiveSheet({ open: false })}
        onSaved={refresh}
      />
      <CalendarEventSheet
        open={eventSheet.open}
        eventId={eventSheet.id}
        defaultDate={eventSheet.date}
        onClose={() => setEventSheet({ open: false })}
        onSaved={refresh}
      />
      <ActivityForm
        open={activitySheet.open}
        defaultDate={activitySheet.date}
        onClose={() => setActivitySheet({ open: false })}
      />
      <CoachSheet
        open={coachOpen}
        autoStart={coachAutoStart}
        onClose={() => setCoachOpen(false)}
        onSaved={refresh}
      />
      <CoachSheet
        open={!!modifyProgram}
        program={modifyProgram}
        onClose={() => setModifyProgram(null)}
        onSaved={refresh}
      />
    </div>
  )
}

// --------------------------------------------------------------------------- //
function ObjectiveSection({
  onEdit,
  onGenerate,
}: {
  onEdit: (id?: number) => void
  onGenerate: () => void
}) {
  const qc = useQueryClient()
  const { data: active } = useQuery({
    queryKey: ['active-objective'],
    queryFn: api.activeObjective,
  })
  // All objectives — to count each top-level objective's training milestones.
  const { data: all = [] } = useQuery({ queryKey: ['objectives'], queryFn: api.listObjectives })
  const { data: programs = [] } = useQuery({ queryKey: ['programs'], queryFn: api.listPrograms })

  const objectives = active?.objectives ?? []
  const focusId = active?.objective?.id ?? null
  const hasActivePlan = programs.some((p) => p.status === 'active')

  const milestoneCount = (id: number) =>
    all.filter((o) => o.parent_objective_id === id).length

  async function remove(o: Objective) {
    if (
      !confirm(
        `Delete "${o.name}"? Its plans + history stay; any training milestones become standalone objectives.`,
      )
    )
      return
    await api.deleteObjective(o.id)
    qc.invalidateQueries({ queryKey: ['active-objective'] })
    qc.invalidateQueries({ queryKey: ['objectives'] })
  }

  return (
    <div className="mt-6">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">Objectives</h2>
        <button className="text-sm text-amber-300 hover:text-amber-200" onClick={() => onEdit()}>
          + Add
        </button>
      </div>

      {objectives.length === 0 ? (
        <button
          onClick={() => onEdit()}
          className="block w-full rounded-xl border border-dashed border-slate-700 p-3 text-left text-sm text-slate-400 hover:bg-slate-800/40"
        >
          Set a goal (e.g. “Climb Baker”) — the coach will periodize a plan toward it.
        </button>
      ) : (
        <div className="space-y-2">
          {objectives.map((o) => {
            const isFocus = o.id === focusId
            const ms = milestoneCount(o.id)
            return (
              <div
                key={o.id}
                className={`rounded-xl border p-3 ${
                  isFocus
                    ? 'border-amber-700/40 bg-amber-900/15'
                    : 'border-slate-800 bg-slate-800/40'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <button onClick={() => onEdit(o.id)} className="block min-w-0 flex-1 text-left">
                    <div
                      className={`flex items-center gap-2 text-sm font-semibold ${
                        isFocus ? 'text-amber-200' : 'text-slate-100'
                      }`}
                    >
                      <span>{isFocus ? '🎯' : '📌'}</span>
                      <span className="truncate">{o.name}</span>
                      {isFocus && (
                        <span className="shrink-0 rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-amber-300">
                          Focus
                        </span>
                      )}
                    </div>
                    <div className="mt-0.5 text-xs text-slate-400">
                      {o.kind === 'dated' && o.target_date
                        ? objectiveDateLabel(o.target_date, o.event_end_date)
                        : 'open-ended'}
                      {o.sport && ` · ${o.sport}`}
                      {ms > 0 && ` · ${ms} milestone${ms === 1 ? '' : 's'}`}
                    </div>
                  </button>
                  <button
                    className="shrink-0 text-slate-600 hover:text-red-400"
                    onClick={() => remove(o)}
                    aria-label={`Delete ${o.name}`}
                  >
                    ✕
                  </button>
                </div>

                {isFocus && (active?.constraints.length ?? 0) > 0 && (
                  <div className="mt-1 text-xs text-slate-400">
                    Training around: {active!.constraints.map((c) => c.label).join(', ')}
                  </div>
                )}

                {isFocus && active?.active_program?.coach_summary && (
                  <div className="mt-2 rounded-lg border border-slate-700/60 bg-slate-800/40 p-2.5">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                      Coach&apos;s strategy
                    </p>
                    <p className="mt-0.5 text-xs leading-relaxed text-slate-300">
                      {active.active_program.coach_summary}
                    </p>
                  </div>
                )}

                {isFocus && (
                  <>
                    <Button className="mt-3 w-full" onClick={onGenerate}>
                      {hasActivePlan ? '✨ Regenerate plan' : '✨ Generate plan'}
                    </Button>
                    <p className="mt-1.5 text-center text-[11px] text-slate-500">
                      The coach builds &amp; periodizes a plan toward your focus objective.
                    </p>
                  </>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function objectiveDateLabel(iso: string, eventEnd?: string | null): string {
  const d = new Date(iso + 'T00:00:00')
  const fmt = (x: Date) =>
    x.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
  const weeks = Math.max(0, Math.round((d.getTime() - Date.now()) / (7 * 864e5)))
  const range = eventEnd ? `${fmt(d)} – ${fmt(new Date(eventEnd + 'T00:00:00'))}` : fmt(d)
  return `${range} · ~${weeks} wk${weeks === 1 ? '' : 's'} out`
}

// --------------------------------------------------------------------------- //
// Athletic-calendar events: constraints the coach trains AROUND (races, weekly
// league games, trips, rehab windows) — distinct from Objectives, which are
// goals the coach peaks TOWARD. Listed here as a flat upcoming list; they also
// render as markers on the month grid above (see CalendarGrid / DaySheet).
function EventsSection({ onAdd }: { onAdd: () => void }) {
  const { data: events = [] } = useQuery({
    queryKey: ['calendar-events'],
    queryFn: api.listCalendarEvents,
  })

  const todayIso = isoDate(new Date())
  const upcoming = events
    .filter((e) => e.recurrence === 'weekly' || e.event_date >= todayIso)
    .sort((a, b) => a.event_date.localeCompare(b.event_date))

  return (
    <div className="mt-6">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          Athletic calendar
        </h2>
        <button className="text-sm text-amber-300 hover:text-amber-200" onClick={onAdd}>
          + Add
        </button>
      </div>

      {upcoming.length === 0 ? (
        <button
          onClick={onAdd}
          className="block w-full rounded-xl border border-dashed border-slate-700 p-3 text-left text-sm text-slate-400 hover:bg-slate-800/40"
        >
          Add a race, league game, trip, or rehab window — the coach trains around it.
        </button>
      ) : (
        <div className="space-y-2">
          {upcoming.map((e) => (
            <div
              key={e.id}
              className="flex items-center justify-between gap-2 rounded-xl border border-sky-700/40 bg-sky-900/15 p-3"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-sm font-semibold text-sky-200">
                  <span>📍</span>
                  <span className="truncate">{e.name}</span>
                </div>
                <div className="mt-0.5 text-xs text-sky-300/70">
                  {e.type}
                  {e.recurrence === 'weekly' ? ' · weekly' : ` · ${e.event_date}`}
                  {e.load && ` · ${e.load.regions}/${e.load.intensity}`}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// --------------------------------------------------------------------------- //
function ProgramsSection({
  onModify,
  onChanged,
}: {
  onModify: (p: { id: number; name: string }) => void
  onChanged: () => void
}) {
  const { data: programs = [] } = useQuery({ queryKey: ['programs'], queryFn: api.listPrograms })
  const active = programs.filter((p) => p.status === 'active')
  if (active.length === 0) return null

  async function remove(id: number) {
    if (!confirm('Delete this program? Completed workouts stay in your history.')) return
    await api.deleteProgram(id)
    onChanged()
  }

  return (
    <div className="mt-6">
      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400">Programs</h2>
      <div className="space-y-2">
        {active.map((p) => (
          <div key={p.id} className="rounded-xl border border-slate-800 bg-slate-800/40 p-3">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate font-semibold text-slate-100">{p.name}</div>
                <div className="text-xs text-slate-400">
                  {p.completed_count}/{p.planned_count} done
                  {p.end_date && ` · ends ${p.end_date}`}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <button
                  className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-amber-300 hover:bg-slate-800"
                  onClick={() => onModify({ id: p.id, name: p.name })}
                >
                  Modify
                </button>
                <button className="text-slate-600 hover:text-red-400" onClick={() => remove(p.id)} aria-label="Delete">
                  ✕
                </button>
              </div>
            </div>
            {p.coach_summary && (
              <p className="mt-2 border-t border-slate-800 pt-2 text-xs leading-relaxed text-slate-300">
                {p.coach_summary}
              </p>
            )}
          </div>
        ))}
      </div>
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
  eventsByDate,
  onPick,
}: {
  weeks: Date[][]
  month: Date
  today: Date
  byDate: Map<string, CalendarEntry[]>
  eventsByDate: Map<string, CalendarEventOccurrence[]>
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
          const iso = isoDate(d)
          const es = byDate.get(iso) ?? []
          const planned = es.some((e) => e.kind === 'planned' && e.status === 'planned')
          const done = es.some(
            (e) =>
              (e.kind === 'session' && e.status === 'completed') ||
              (e.kind === 'planned' && e.status === 'completed'),
          )
          const active = es.some((e) => e.kind === 'session' && e.status === 'in_progress')
          const peak = es.some((e) => e.kind === 'objective')
          const inBlock = es.some((e) => e.kind === 'objective_block')
          // Athletic-calendar events (constraints) render as a distinct point
          // MARKER — a small hollow ring badge — never the filled objective
          // "band" background, so events and objectives stay visually distinct.
          const eventCount = (eventsByDate.get(iso) ?? []).length
          const isToday = sameDay(d, today)
          return (
            <button
              key={i}
              onClick={() => onPick(d)}
              aria-label={iso}
              className={`relative flex aspect-square flex-col items-center justify-center rounded-lg text-sm ${
                inMonth ? 'text-slate-200' : 'text-slate-600'
              } ${isToday ? 'ring-1 ring-amber-500' : ''} ${
                inBlock ? 'bg-fuchsia-500/10' : es.length ? 'bg-slate-800/60' : 'hover:bg-slate-800/40'
              }`}
            >
              {eventCount > 0 && (
                <span
                  className="absolute right-0.5 top-0.5 h-2 w-2 rounded-full border border-sky-400 bg-transparent"
                  aria-label="athletic event"
                  title="athletic event"
                />
              )}
              <span>{d.getDate()}</span>
              <span className="mt-0.5 flex h-1.5 gap-0.5">
                {planned && <Dot className="bg-amber-400" />}
                {done && <Dot className="bg-emerald-400" />}
                {active && <Dot className="bg-amber-400 animate-pulse" />}
                {peak && <Dot className="bg-fuchsia-400" />}
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
    <div className="mt-3 flex flex-wrap justify-center gap-4 text-[11px] text-slate-500">
      <span className="flex items-center gap-1">
        <Dot className="bg-amber-400" /> planned
      </span>
      <span className="flex items-center gap-1">
        <Dot className="bg-emerald-400" /> completed
      </span>
      <span className="flex items-center gap-1">
        <Dot className="bg-fuchsia-400" /> objective
      </span>
      <span className="flex items-center gap-1">
        <span className="h-2 w-2 rounded-full border border-sky-400 bg-transparent" /> athletic
        event
      </span>
    </div>
  )
}

// --------------------------------------------------------------------------- //
function DaySheet({
  date,
  entries,
  occurrences,
  onClose,
  onChanged,
  onStarted,
  onEditEvent,
  onAddEvent,
  onAddActivity,
  onAddObjective,
}: {
  date: Date | null
  entries: CalendarEntry[]
  occurrences: CalendarEventOccurrence[]
  onClose: () => void
  onChanged: () => void
  onStarted: (sessionId: number) => void
  onEditEvent: (id: number) => void
  onAddEvent: () => void
  onAddActivity: () => void
  onAddObjective: () => void
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
  // One objective chip per objective on this day: a peak/event marker wins over a
  // bare block day (a day can be both — the peak day of a block).
  const objectiveById = new Map<number, CalendarEntry>()
  for (const e of entries) {
    if (e.kind !== 'objective' && e.kind !== 'objective_block') continue
    const prev = objectiveById.get(e.id)
    if (!prev || e.kind === 'objective') objectiveById.set(e.id, e)
  }
  const objectives = [...objectiveById.values()]

  const objectiveLabel = (e: CalendarEntry) =>
    e.kind === 'objective'
      ? e.status === 'peak'
        ? '🎯 peak / target day'
        : '🎯 event day'
      : '🏋 training block'

  return (
    <Sheet open={!!date} onClose={onClose} title={title}>
      <div className="space-y-4">
        {entries.length === 0 && occurrences.length === 0 && (
          <EmptyState title="Nothing scheduled" hint="Schedule a routine below or ask the Coach." />
        )}

        {objectives.map((e) => (
          <div
            key={`o${e.id}`}
            className="rounded-xl border border-fuchsia-700/40 bg-fuchsia-900/15 p-3"
          >
            <div className="text-sm font-semibold text-fuchsia-200">
              {e.objective_name ?? e.name}
            </div>
            <div className="mt-0.5 text-xs text-fuchsia-300/80">{objectiveLabel(e)}</div>
          </div>
        ))}

        {/* Athletic-calendar events render as MARKER chips (point-in-time,
            outlined) — visually distinct from the filled objective bands above. */}
        {occurrences.map((o) => (
          <button
            key={`e${o.event.id}`}
            onClick={() => onEditEvent(o.event.id)}
            className="block w-full rounded-xl border border-sky-700/40 bg-sky-900/10 p-3 text-left"
          >
            <div className="flex items-center gap-2 text-sm font-semibold text-sky-200">
              <span className="h-2 w-2 shrink-0 rounded-full border border-sky-400 bg-transparent" />
              <span className="truncate">{o.event.name}</span>
            </div>
            <div className="mt-0.5 text-xs text-sky-300/70">
              {o.event.type}
              {o.event.recurrence === 'weekly' && ' · weekly'}
              {o.event.load && ` · ${o.event.load.regions}/${o.event.load.intensity}`}
              {o.event.load?.duration_min ? ` · ${o.event.load.duration_min}min` : ''}
            </div>
          </button>
        ))}

        <div className="flex gap-2">
          <button
            onClick={onAddActivity}
            className="flex-1 rounded-xl border border-dashed border-slate-700 p-2.5 text-center text-xs text-slate-300 hover:bg-slate-800/40"
          >
            🏃 Log activity
          </button>
          <button
            onClick={onAddObjective}
            className="flex-1 rounded-xl border border-dashed border-fuchsia-800/60 p-2.5 text-center text-xs text-fuchsia-300/80 hover:bg-fuchsia-900/10"
          >
            🎯 New objective
          </button>
        </div>

        <button
          onClick={onAddEvent}
          className="block w-full rounded-xl border border-dashed border-sky-800/60 p-2.5 text-center text-xs text-sky-300/80 hover:bg-sky-900/10"
        >
          + Add athletic event on this day
        </button>

        {planned.map((e) => (
          <PlannedCard
            key={`p${e.id}`}
            e={e}
            busy={busy}
            onStart={() => start(e.id)}
            onRemove={() => remove(e.id)}
          />
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

// --------------------------------------------------------------------------- //
// A planned day in the DaySheet: tap the header to review the prescribed routine
// (exercises + sets×reps×weight) without starting it; "Start workout" is separate.
function PlannedCard({
  e,
  busy,
  onStart,
  onRemove,
}: {
  e: CalendarEntry
  busy: boolean
  onStart: () => void
  onRemove: () => void
}) {
  const [open, setOpen] = useState(false)
  const unit = useSettings().weight_unit
  const { data: detail, isLoading } = useQuery({
    queryKey: ['planned', e.id],
    queryFn: () => api.getPlanned(e.id),
    enabled: open,
  })
  const done = e.status === 'completed'

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-800/40 p-3">
      <div className="flex items-start justify-between gap-2">
        <button
          className="min-w-0 flex-1 text-left"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
        >
          <div className="flex items-center gap-1.5 font-semibold text-slate-100">
            <span className={`text-slate-500 transition-transform ${open ? 'rotate-90' : ''}`}>›</span>
            <span className="truncate">{e.name || 'Workout'}</span>
          </div>
          <div className="ml-4 text-xs text-slate-400">
            {e.exercise_count} exercises · {e.status} ·{' '}
            <span className="text-amber-300">{open ? 'hide' : 'view routine'}</span>
          </div>
        </button>
        <button
          className="text-slate-600 hover:text-red-400"
          onClick={onRemove}
          disabled={busy}
          aria-label="Delete"
        >
          ✕
        </button>
      </div>

      {open && (
        <div className="mt-2 border-t border-slate-800 pt-2">
          {isLoading || !detail ? (
            <p className="text-xs text-slate-500">Loading…</p>
          ) : detail.exercises.length === 0 ? (
            <p className="text-xs text-slate-500">No exercises in this routine.</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {detail.exercises.map((pe) => (
                <li key={pe.id} className="flex justify-between gap-3">
                  <span className="min-w-0 truncate text-slate-200">{pe.exercise.name}</span>
                  <span className="shrink-0 text-slate-400">{prescriptionLine(pe, unit)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {!done ? (
        <Button className="mt-3 w-full" onClick={onStart} disabled={busy}>
          Start workout
        </Button>
      ) : (
        <p className="mt-2 text-xs text-emerald-400">Completed ✓</p>
      )}
    </div>
  )
}

function prescriptionLine(pe: PlannedExercise, unit: string): string {
  const sets = pe.target_sets ?? '?'
  if (pe.target_duration_seconds) return `${sets}×${pe.target_duration_seconds}s`
  const reps = pe.target_reps ?? '?'
  const w = pe.target_weight != null ? ` @ ${pe.target_weight}${unit}` : ''
  return `${sets}×${reps}${w}`
}
