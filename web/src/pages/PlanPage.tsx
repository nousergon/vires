import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  api,
  type CalendarEntry,
  type Objective,
  type PlannedExercise,
  type PlannedWorkout,
  type PendingAilmentCheckIn,
} from '../lib/api'
import { Button, EmptyState, PageTitle, Sheet, Spinner } from '../components/ui'
import CoachSheet from '../components/CoachSheet'
import CoachSummaryView from '../components/CoachSummaryView'
import ObjectiveSheet from '../components/ObjectiveSheet'
import ActivityForm from '../components/ActivityForm'
import AilmentsPanel, { AilmentCheckInForm, AilmentSheet } from '../components/AilmentsPanel'
import SessionDetailSheet from '../components/SessionDetailSheet'
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
  // new (optionally seeded with the tapped day via `date`, dated objectives only,
  // or forced to a `kind` — e.g. the Status tab's "general objectives" list,
  // which always seeds `open_ended` since it has no date to anchor to).
  const [objectiveSheet, setObjectiveSheet] = useState<{
    open: boolean
    id?: number
    date?: string
    kind?: 'dated' | 'open_ended'
  }>({
    open: false,
  })
  // Add/edit-activity sheet — id present = edit that session (via PATCH),
  // absent = add new (optionally seeded with the tapped day via `date`). One
  // sheet covers both a logged activity and a future/recurring/objective-
  // anchored one (formerly a separate athletic-calendar event) — whether
  // it's planned or happened is derived from date, not a separate flow.
  const [activitySheet, setActivitySheet] = useState<{ open: boolean; id?: number; date?: string }>({
    open: false,
  })
  // New-ailment sheet — always a create flow (ailments are edited/checked-in
  // inline via AilmentsPanel, never re-opened here); `date` seeds onset_date
  // when opened from a calendar day tap.
  const [ailmentSheet, setAilmentSheet] = useState<{ open: boolean; date?: string }>({ open: false })
  const [modifyProgram, setModifyProgram] = useState<{ id: number; name: string } | null>(null)
  const [movedBanner, setMovedBanner] = useState<PlannedWorkout[]>([])
  // A completed routine tapped in the DaySheet — opens the shared logged-
  // session detail (view + tag: tags / pre-workout fuel / energy / intensity).
  const [sessionDetailId, setSessionDetailId] = useState<number | null>(null)
  const [planView, setPlanView] = useState<'calendar' | 'coach' | 'status'>('calendar')

  const openObjective = (id?: number, date?: string, kind?: 'dated' | 'open_ended') =>
    setObjectiveSheet({ open: true, id, date, kind })
  const openActivity = (id?: number, date?: string) => setActivitySheet({ open: true, id, date })
  const openAilment = (date?: string) => setAilmentSheet({ open: true, date })

  // Tapping a virtual (never-materialized) recurring occurrence turns it
  // into a real, linked row first, then opens it for editing — a real id
  // and a merely-projected one both end up going through the same sheet.
  async function openActivityEntry(e: CalendarEntry) {
    if (e.virtual) {
      const ws = await api.materializeOccurrence(e.id, e.date)
      qc.invalidateQueries({ queryKey: ['calendar'] })
      openActivity(ws.id, e.date)
    } else {
      openActivity(e.id, e.date)
    }
  }

  const openCoach = (auto: boolean) => {
    setCoachAutoStart(auto)
    setCoachOpen(true)
  }

  // Mechanically slides any missed workout onto the next fit-to-train-on day
  // — no LLM, no confirmation. Fired once per mount; idempotent server-side,
  // so a StrictMode dev double-invoke is a harmless extra no-op call.
  const rescheduleMissed = useMutation({
    mutationFn: api.rescheduleMissed,
    onSuccess: (moved) => {
      if (moved.length > 0) {
        setMovedBanner(moved)
        qc.invalidateQueries({ queryKey: ['calendar'] })
      }
    },
  })
  const checkedReschedule = useRef(false)
  useEffect(() => {
    if (checkedReschedule.current) return
    checkedReschedule.current = true
    rescheduleMissed.mutate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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

  const { data: programs = [] } = useQuery({ queryKey: ['programs'], queryFn: api.listPrograms })

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['calendar'] })
    qc.invalidateQueries({ queryKey: ['programs'] })
    qc.invalidateQueries({ queryKey: ['active-objective'] })
    qc.invalidateQueries({ queryKey: ['ailments'] })
    qc.invalidateQueries({ queryKey: ['ailments-pending'] })
  }

  function onStarted(sessionId: number) {
    localStorage.setItem(ACTIVE_KEY, String(sessionId))
    nav('/train')
  }

  return (
    <div>
      <PageTitle right={<Button onClick={() => openCoach(false)}>✨ Coach</Button>}>Plan</PageTitle>

      {movedBanner.length > 0 && (
        <RescheduleBanner moved={movedBanner} onDismiss={() => setMovedBanner([])} />
      )}

      <div className="mb-4 flex rounded-xl border border-slate-800 bg-slate-900/60 p-1">
        {(['calendar', 'coach', 'status'] as const).map((v) => (
          <button
            key={v}
            onClick={() => setPlanView(v)}
            className={`flex-1 rounded-lg py-2 text-sm font-medium capitalize ${
              planView === v
                ? 'bg-slate-800 text-amber-200'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {v === 'calendar' ? 'Calendar' : v === 'coach' ? 'Coach' : 'Status'}
          </button>
        ))}
      </div>

      {planView === 'calendar' ? (
        <>
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
              onPick={setSelected}
            />
          )}

          <Legend />

          <ObjectiveSection onEdit={openObjective} onGenerate={() => openCoach(true)} />

          <EventsSection entries={entries} onEdit={openActivityEntry} onAdd={() => openActivity()} />

          <ProgramsSection onModify={setModifyProgram} onChanged={refresh} compact />
        </>
      ) : planView === 'coach' ? (
        <CoachSummaryView
          programs={programs}
          onGenerateCoach={() => openCoach(true)}
          onModifyProgram={setModifyProgram}
          onChanged={refresh}
        />
      ) : (
        <StatusView onAddAilment={() => openAilment()} onChanged={refresh} onEditObjective={openObjective} />
      )}

      <DaySheet
        date={selected}
        entries={selected ? byDate.get(isoDate(selected)) ?? [] : []}
        onClose={() => setSelected(null)}
        onChanged={refresh}
        onStarted={onStarted}
        onEditActivity={openActivityEntry}
        onOpenSession={setSessionDetailId}
        onAddActivity={() => (selected ? openActivity(undefined, isoDate(selected)) : openActivity())}
        onAddObjective={() => (selected ? openObjective(undefined, isoDate(selected)) : openObjective())}
        onAddAilment={() => (selected ? openAilment(isoDate(selected)) : openAilment())}
      />
      <SessionDetailSheet sessionId={sessionDetailId} onClose={() => setSessionDetailId(null)} />
      <ObjectiveSheet
        open={objectiveSheet.open}
        objectiveId={objectiveSheet.id}
        defaultDate={objectiveSheet.date}
        defaultKind={objectiveSheet.kind}
        onClose={() => setObjectiveSheet({ open: false })}
        onSaved={refresh}
      />
      <ActivityForm
        open={activitySheet.open}
        sessionId={activitySheet.id}
        defaultDate={activitySheet.date}
        onClose={() => setActivitySheet({ open: false })}
        onSaved={refresh}
      />
      <AilmentSheet
        open={ailmentSheet.open}
        defaultDate={ailmentSheet.date}
        onClose={() => setAilmentSheet({ open: false })}
        onSaved={refresh}
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
// Upcoming activities/events: constraints the coach trains AROUND (races,
// weekly league games, trips, rehab windows) — distinct from Objectives,
// which are goals the coach peaks TOWARD. Same 'session' kind as a logged
// activity — filtered to status='upcoming' — so this is a discovery list
// over the SAME feed the month grid renders, not a separate concept. Listed
// here as a flat list; upcoming activities also render as markers on the
// month grid above (see CalendarGrid / DaySheet).
function EventsSection({
  entries,
  onEdit,
  onAdd,
}: {
  entries: CalendarEntry[]
  onEdit: (e: CalendarEntry) => void
  onAdd: () => void
}) {
  const upcoming = entries
    .filter((e) => e.kind === 'session' && e.session_type === 'activity' && e.status === 'upcoming')
    .sort((a, b) => a.date.localeCompare(b.date))

  return (
    <div className="mt-6">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          Upcoming activities
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
            <button
              key={`${e.id}-${e.date}`}
              onClick={() => onEdit(e)}
              className="flex w-full items-center justify-between gap-2 rounded-xl border border-sky-700/40 bg-sky-900/15 p-3 text-left"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-sm font-semibold text-sky-200">
                  <span>📍</span>
                  <span className="truncate">{e.name}</span>
                </div>
                <div className="mt-0.5 text-xs text-sky-300/70">{e.date}</div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// --------------------------------------------------------------------------- //
// Status tab: ailments + standing (non-dated) objectives — context the coach
// factors in but that has no calendar anchor of its own (dated objectives +
// their bands stay on the Calendar tab, where they're spatially meaningful).
function StatusView({
  onAddAilment,
  onChanged,
  onEditObjective,
}: {
  onAddAilment: () => void
  onChanged: () => void
  onEditObjective: (id?: number, date?: string, kind?: 'dated' | 'open_ended') => void
}) {
  return (
    <div className="space-y-6">
      <AilmentsPanel onAdd={onAddAilment} onChanged={onChanged} />
      <GeneralObjectivesSection onEdit={onEditObjective} />
    </div>
  )
}

function GeneralObjectivesSection({
  onEdit,
}: {
  onEdit: (id?: number, date?: string, kind?: 'dated' | 'open_ended') => void
}) {
  const qc = useQueryClient()
  const { data: all = [] } = useQuery({ queryKey: ['objectives'], queryFn: api.listObjectives })
  const standing = all.filter((o) => o.kind === 'open_ended')

  const milestoneCount = (id: number) => all.filter((o) => o.parent_objective_id === id).length

  async function remove(o: Objective) {
    if (!confirm(`Delete "${o.name}"? Its plans + history stay.`)) return
    await api.deleteObjective(o.id)
    qc.invalidateQueries({ queryKey: ['active-objective'] })
    qc.invalidateQueries({ queryKey: ['objectives'] })
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          General objectives
        </h2>
        <button
          className="text-sm text-amber-300 hover:text-amber-200"
          onClick={() => onEdit(undefined, undefined, 'open_ended')}
        >
          + Add
        </button>
      </div>
      <p className="mb-2 text-xs text-slate-500">
        Standing goals with no target date — e.g. "build a bigger squat." The coach
        falls back to one of these as its focus when nothing dated is closer.
      </p>

      {standing.length === 0 ? (
        <button
          onClick={() => onEdit(undefined, undefined, 'open_ended')}
          className="block w-full rounded-xl border border-dashed border-slate-700 p-3 text-left text-sm text-slate-400 hover:bg-slate-800/40"
        >
          Add a standing goal — no date required.
        </button>
      ) : (
        <div className="space-y-2">
          {standing.map((o) => {
            const ms = milestoneCount(o.id)
            return (
              <div key={o.id} className="rounded-xl border border-slate-800 bg-slate-800/40 p-3">
                <div className="flex items-start justify-between gap-2">
                  <button onClick={() => onEdit(o.id)} className="block min-w-0 flex-1 text-left">
                    <div className="truncate text-sm font-semibold text-slate-100">{o.name}</div>
                    <div className="mt-0.5 text-xs text-slate-400">
                      {o.sport && `${o.sport}`}
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
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// --------------------------------------------------------------------------- //
function ProgramsSection({
  onModify,
  onChanged,
  compact = false,
}: {
  onModify: (p: { id: number; name: string }) => void
  onChanged: () => void
  compact?: boolean
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
            {p.coach_summary && !compact && (
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
          const iso = isoDate(d)
          const es = byDate.get(iso) ?? []
          const planned = es.some((e) => e.kind === 'planned' && e.status === 'planned')
          const done = es.some(
            (e) =>
              (e.kind === 'session' && e.status === 'completed') ||
              (e.kind === 'planned' && e.status === 'completed'),
          )
          // A fulfilled planned entry carries its session's live status (the
          // session row itself is absorbed), so the pulse covers both kinds.
          const active = es.some(
            (e) => (e.kind === 'session' || e.kind === 'planned') && e.status === 'in_progress',
          )
          const peak = es.some((e) => e.kind === 'objective')
          const inBlock = es.some((e) => e.kind === 'objective_block')
          // Upcoming activities/events (constraints) render as a distinct
          // point MARKER — a small hollow ring badge — never the filled
          // objective "band" background, so events and objectives stay
          // visually distinct. Same 'session' kind as a logged activity,
          // filtered to status='upcoming' (covers both a materialized future
          // row and a virtual not-yet-materialized occurrence).
          const eventCount = es.filter(
            (e) => e.kind === 'session' && e.session_type === 'activity' && e.status === 'upcoming',
          ).length
          const hasAilment = es.some((e) => e.kind === 'ailment')
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
              {hasAilment && (
                <span
                  className="absolute left-0.5 top-0.5 h-2 w-2 rounded-full border border-rose-400 bg-transparent"
                  aria-label="ailment"
                  title="ailment"
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

// A day is shown "moved from ..." → "..." in local weekday/month/day form —
// dates arrive as plain YYYY-MM-DD, so parse at local midnight rather than
// letting `new Date(iso)` interpret it as UTC (which can shift the day back
// by a timezone offset).
function fmtLocalDate(iso: string): string {
  return new Date(iso + 'T00:00:00').toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  })
}

function RescheduleBanner({
  moved,
  onDismiss,
}: {
  moved: PlannedWorkout[]
  onDismiss: () => void
}) {
  return (
    <div className="mb-4 rounded-xl border border-amber-700/40 bg-amber-900/15 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 text-sm text-amber-200">
          <p className="font-semibold">
            🧠 The coach moved {moved.length === 1 ? 'a missed workout' : `${moved.length} missed workouts`}
          </p>
          <ul className="mt-1 space-y-0.5 text-xs text-amber-300/80">
            {moved.map((pw) => (
              <li key={pw.id} className="truncate">
                {pw.name} — {pw.rescheduled_from ? fmtLocalDate(pw.rescheduled_from) : '?'} →{' '}
                {fmtLocalDate(pw.scheduled_date)}
              </li>
            ))}
          </ul>
        </div>
        <button
          className="shrink-0 text-amber-400/70 hover:text-amber-200"
          onClick={onDismiss}
          aria-label="Dismiss"
        >
          ✕
        </button>
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
        <span className="h-2 w-2 rounded-full border border-sky-400 bg-transparent" /> upcoming
        activity
      </span>
      <span className="flex items-center gap-1">
        <span className="h-2 w-2 rounded-full border border-rose-400 bg-transparent" /> ailment
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
  onEditActivity,
  onOpenSession,
  onAddActivity,
  onAddObjective,
  onAddAilment,
}: {
  date: Date | null
  entries: CalendarEntry[]
  onClose: () => void
  onChanged: () => void
  onStarted: (sessionId: number) => void
  onEditActivity: (e: CalendarEntry) => void
  onOpenSession: (sessionId: number) => void
  onAddActivity: () => void
  onAddObjective: () => void
  onAddAilment: () => void
}) {
  const { data: templates = [] } = useQuery({ queryKey: ['templates'], queryFn: api.listTemplates })
  const [busy, setBusy] = useState(false)
  const [checkInGate, setCheckInGate] = useState<{
    pending: PendingAilmentCheckIn[]
    plannedId: number
  } | null>(null)
  const title = date
    ? date.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })
    : ''

  async function doStart(plannedId: number) {
    setBusy(true)
    try {
      const ws = await api.startPlanned(plannedId)
      onStarted(ws.id)
    } finally {
      setBusy(false)
    }
  }

  async function start(plannedId: number) {
    const pending = await api.pendingAilmentCheckIns(isoDate(new Date()))
    if (pending.length > 0) {
      setCheckInGate({ pending, plannedId })
      return
    }
    await doStart(plannedId)
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
  const sessions = entries.filter((e) => e.kind === 'session' && e.session_type !== 'activity')
  // Activities — logged OR upcoming/planned/recurring (formerly a separate
  // athletic-calendar event) — same 'session' kind, split out from strength
  // sessions above purely for a distinct chip style, not a distinct concept.
  const activities = entries.filter((e) => e.kind === 'session' && e.session_type === 'activity')
  // One objective chip per objective on this day: a peak/event marker wins over a
  // bare block day (a day can be both — the peak day of a block).
  const objectiveById = new Map<number, CalendarEntry>()
  for (const e of entries) {
    if (e.kind !== 'objective' && e.kind !== 'objective_block') continue
    const prev = objectiveById.get(e.id)
    if (!prev || e.kind === 'objective') objectiveById.set(e.id, e)
  }
  const objectives = [...objectiveById.values()]
  const ailments = entries.filter((e) => e.kind === 'ailment')

  const objectiveLabel = (e: CalendarEntry) =>
    e.kind === 'objective'
      ? e.status === 'peak'
        ? '🎯 peak / target day'
        : '🎯 event day'
      : '🏋 training block'

  return (
    <>
      <Sheet open={!!date} onClose={onClose} title={title}>
      <div className="space-y-4">
        {entries.length === 0 && (
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

        {/* Activities render as MARKER chips (point-in-time, outlined) —
            visually distinct from the filled objective bands above. Covers a
            logged activity AND a future/recurring/objective-anchored one
            (formerly a separate athletic-calendar event) — same chip either
            way, since whether it's planned or happened is just its date vs.
            now. Tapping a virtual (never-materialized) occurrence
            materializes it first (see onEditActivity in PlanPage). */}
        {activities.map((e) => (
          <button
            key={`e${e.id}-${e.date}`}
            onClick={() => onEditActivity(e)}
            className="block w-full rounded-xl border border-sky-700/40 bg-sky-900/10 p-3 text-left"
          >
            <div className="flex items-center gap-2 text-sm font-semibold text-sky-200">
              <span className="h-2 w-2 shrink-0 rounded-full border border-sky-400 bg-transparent" />
              <span className="truncate">{e.name || 'Activity'}</span>
            </div>
            <div className="mt-0.5 text-xs text-sky-300/70">
              {e.status === 'completed'
                ? 'logged'
                : e.status === 'upcoming'
                  ? 'upcoming'
                  : 'needs logging'}
            </div>
          </button>
        ))}

        {/* Ailment bands for this day — same rose styling as AilmentsPanel. */}
        {ailments.map((e) => (
          <div key={`a${e.id}`} className="rounded-xl border border-rose-800/40 bg-rose-900/10 p-3">
            <div className="text-sm font-semibold text-rose-100">{e.name}</div>
            <div className="mt-0.5 text-xs text-rose-200/70">{e.status}</div>
          </div>
        ))}

        <div className="flex gap-2">
          <button
            onClick={onAddActivity}
            className="flex-1 rounded-xl border border-dashed border-slate-700 p-2.5 text-center text-xs text-slate-300 hover:bg-slate-800/40"
          >
            🏃 Add activity
          </button>
          <button
            onClick={onAddObjective}
            className="flex-1 rounded-xl border border-dashed border-fuchsia-800/60 p-2.5 text-center text-xs text-fuchsia-300/80 hover:bg-fuchsia-900/10"
          >
            🎯 New objective
          </button>
          <button
            onClick={onAddAilment}
            className="flex-1 rounded-xl border border-dashed border-rose-800/60 p-2.5 text-center text-xs text-rose-300/80 hover:bg-rose-900/10"
          >
            🩹 Add ailment
          </button>
        </div>

        {planned.map((e) => (
          <PlannedCard
            key={`p${e.id}`}
            e={e}
            busy={busy}
            onStart={() => start(e.id)}
            onResume={() => e.session_id != null && onStarted(e.session_id)}
            onOpenSession={() => e.session_id != null && onOpenSession(e.session_id)}
            onRemove={() => remove(e.id)}
          />
        ))}

        {/* Ad-hoc sessions (no fulfilled plan behind them — those are absorbed
            into their PlannedCard above). Tap a completed one to view + tag it
            (pre-workout fuel / energy / intensity); tap an in-progress one to
            resume it. */}
        {sessions.map((e) => (
          <button
            key={`s${e.id}`}
            onClick={() => (e.status === 'in_progress' ? onStarted(e.id) : onOpenSession(e.id))}
            className="block w-full rounded-xl border border-slate-800 bg-slate-800/40 p-3 text-left hover:bg-slate-800/70"
          >
            <div className="font-semibold text-slate-100">{e.name || 'Workout'}</div>
            <div className="text-xs text-slate-400">
              {e.exercise_count} exercises ·{' '}
              {e.status === 'completed' ? (
                <span className="text-emerald-400">logged</span>
              ) : (
                <span className="text-amber-400">in progress</span>
              )}
              <span className="ml-2 text-amber-300">
                {e.status === 'in_progress' ? 'resume →' : 'view / tag →'}
              </span>
            </div>
          </button>
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
      <Sheet
        open={checkInGate != null}
        onClose={() => setCheckInGate(null)}
        title="Ailment check-in"
      >
        {checkInGate && (
          <AilmentCheckInForm
            pending={checkInGate.pending}
            onCancel={() => setCheckInGate(null)}
            onDone={() => {
              const id = checkInGate.plannedId
              setCheckInGate(null)
              onChanged()
              void doStart(id)
            }}
          />
        )}
      </Sheet>
    </>
  )
}

// --------------------------------------------------------------------------- //
// A planned day in the DaySheet: tap the header to review the prescribed routine
// (exercises + sets×reps×weight) without starting it; "Start workout" is separate.
function PlannedCard({
  e,
  busy,
  onStart,
  onResume,
  onOpenSession,
  onRemove,
}: {
  e: CalendarEntry
  busy: boolean
  onStart: () => void
  onResume: () => void
  onOpenSession: () => void
  onRemove: () => void
}) {
  const [open, setOpen] = useState(false)
  const unit = useSettings().weight_unit
  const { data: detail, isLoading } = useQuery({
    queryKey: ['planned', e.id],
    queryFn: () => api.getPlanned(e.id),
    enabled: open,
  })
  // The entry's status is the linked session's LIVE status (the calendar
  // absorbs a fulfilled session into this one entry), so a started-but-
  // unfinished routine shows in_progress here, not a premature 'completed'.
  const done = e.status === 'completed'
  const inProgress = e.status === 'in_progress'

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
            {e.exercise_count} exercises · {e.status.replace('_', ' ')} ·{' '}
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

      {inProgress ? (
        <Button className="mt-3 w-full" onClick={onResume} disabled={busy}>
          Resume workout
        </Button>
      ) : !done ? (
        <Button className="mt-3 w-full" onClick={onStart} disabled={busy}>
          Start workout
        </Button>
      ) : (
        <button
          className="mt-2 block w-full text-left text-xs text-emerald-400"
          onClick={onOpenSession}
        >
          Completed ✓ <span className="ml-1 text-amber-300">view / tag →</span>
        </button>
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
