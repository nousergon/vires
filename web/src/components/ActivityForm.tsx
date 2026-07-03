import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  api,
  type LoadIntensity,
  type LoadRegions,
  type Terrain,
  type WorkoutSession,
} from '../lib/api'
import { useSettings } from '../lib/useSettings'
import { fmtLoad } from '../lib/units'
import { isoDate } from '../lib/calendar'
import { Button, Sheet, Spinner } from './ui'
import RouteCapture from './RouteCapture'
import { modeSource, type RouteMode } from '../lib/routeMode'

const REGIONS: { key: LoadRegions; label: string }[] = [
  { key: 'legs', label: 'Legs' },
  { key: 'upper', label: 'Upper' },
  { key: 'full', label: 'Full body' },
  { key: 'core', label: 'Core' },
  { key: 'none', label: 'None' },
]

const INTENSITIES: { key: LoadIntensity; label: string }[] = [
  { key: 'light', label: 'Light' },
  { key: 'moderate', label: 'Moderate' },
  { key: 'hard', label: 'Hard' },
]

// Pack weight + bodyweight are remembered so the highest-friction inputs become
// one tap ("same as last") on the next loaded activity — the load number is
// the only thing no device can supply, so we make entering it cheap. Never
// required: most walks/runs/hikes carry no pack at all.
const LAST_PACK = 'vires.activity.lastPack'
const LAST_BODY = 'vires.activity.lastBody'

const inputCls =
  'w-full rounded-xl border border-slate-700 bg-slate-800 px-4 py-2.5 text-base outline-none focus:border-amber-500'

function num(v: string): number | null {
  const n = parseFloat(v)
  return Number.isFinite(n) ? n : null
}

function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-400">
        {label}
        {hint && <span className="ml-2 normal-case font-normal text-slate-500">{hint}</span>}
      </span>
      {children}
    </label>
  )
}

// Keeps today's time-of-day but takes on the chosen day — there's no real
// start/stop capture in Tier 0.
function startedAtFor(dateStr: string): string {
  const [y, m, d] = dateStr.split('-').map(Number)
  const now = new Date()
  return new Date(y, m - 1, d, now.getHours(), now.getMinutes(), now.getSeconds()).toISOString()
}

export default function ActivityForm({
  open,
  defaultDate,
  sessionId,
  onClose,
  onSaved,
}: {
  open: boolean
  // Seed the log date (e.g. the tapped Plan-calendar day). Omit for "today".
  defaultDate?: string | null
  // Present = edit/prefill this existing session (via PATCH); absent = create new.
  sessionId?: number | null
  onClose: () => void
  onSaved?: () => void
}) {
  const qc = useQueryClient()
  const { weight_unit } = useSettings()
  const editing = sessionId != null

  const [date, setDate] = useState(() => defaultDate ?? isoDate(new Date()))
  const [templateKey, setTemplateKey] = useState('custom')
  const [name, setName] = useState('')
  const [regions, setRegions] = useState<LoadRegions>('full')
  const [intensity, setIntensity] = useState<LoadIntensity>('moderate')
  const [hours, setHours] = useState('')
  const [minutes, setMinutes] = useState('')
  // Route capture — only surfaced for route-capable templates (walk/run/hike).
  const [routeMode, setRouteMode] = useState<RouteMode>('manual')
  const [distance, setDistance] = useState('')
  const [elevation, setElevation] = useState('')
  const [terrain, setTerrain] = useState<Terrain>('trail')
  // Load-carriage — optional on every route-capable template.
  const [pack, setPack] = useState(() => localStorage.getItem(LAST_PACK) ?? '')
  const [body, setBody] = useState(() => localStorage.getItem(LAST_BODY) ?? '')
  // Planning fields (former CalendarEvent axes) — shown when the chosen date
  // is in the future, or when editing a row that already has one of these set.
  // NOTE: there is deliberately NO sport field here — the Activity picker IS
  // the sport for an activity/event (the coach receives template_key). The
  // sport-keyed needs-analysis (demands_profile_for_sport, e.g. 'alpine')
  // belongs to Objectives and is set in ObjectiveSheet. The API still accepts
  // ActivityDetail.sport; this form just never sends it (PATCH is
  // exclude_unset, so existing values are preserved on edit).
  const [recurWeekly, setRecurWeekly] = useState(false)
  const [eventEndDate, setEventEndDate] = useState('')
  const [objectiveId, setObjectiveId] = useState('')
  const [result, setResult] = useState<WorkoutSession | null>(null)

  const packPresets = weight_unit === 'kg' ? [10, 15, 20, 25] : [20, 30, 40, 50]

  const { data: existing, isLoading: loadingExisting } = useQuery({
    queryKey: ['workout', sessionId],
    queryFn: () => api.getWorkout(sessionId as number),
    enabled: open && editing,
  })

  const { data: objectives = [] } = useQuery({
    queryKey: ['objectives'],
    queryFn: api.listObjectives,
    enabled: open,
  })

  // Re-seed everything whenever the sheet (re)opens — it stays mounted while
  // hidden, so a mount-time useState initializer alone wouldn't pick up a
  // changed defaultDate/sessionId, or the fetched `existing` row, on reopen.
  useEffect(() => {
    if (!open) return
    setResult(null)
    if (editing && existing) {
      setDate(isoDate(new Date(existing.started_at)))
      setTemplateKey(existing.activity?.template_key ?? 'custom')
      setName(existing.name ?? '')
      setRegions(existing.activity?.regions ?? 'full')
      setIntensity(existing.activity?.intensity ?? 'moderate')
      const durS = existing.activity?.duration_s ?? 0
      setHours(durS ? String(Math.floor(durS / 3600)) : '')
      setMinutes(durS ? String(Math.floor((durS % 3600) / 60)) : '')
      setDistance('')
      setElevation('')
      setTerrain((existing.activity?.terrain as Terrain) ?? 'trail')
      setRecurWeekly(existing.activity?.recurrence === 'weekly')
      setEventEndDate(existing.activity?.event_end_date ?? '')
      setObjectiveId(existing.activity?.objective_id != null ? String(existing.activity.objective_id) : '')
    } else if (!editing) {
      setDate(defaultDate ?? isoDate(new Date()))
      setTemplateKey('custom')
      setName('')
      setRegions('full')
      setIntensity('moderate')
      setHours('')
      setMinutes('')
      setRouteMode('manual')
      setDistance('')
      setElevation('')
      setTerrain('trail')
      setRecurWeekly(false)
      setEventEndDate('')
      setObjectiveId('')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, editing, existing?.id])

  const { data: templates = [] } = useQuery({
    queryKey: ['activity-templates'],
    queryFn: api.listActivityTemplates,
  })

  const isRouteCapable = templateKey !== 'custom' && !!templates.find((t) => t.key === templateKey)?.route_capable

  function pickTemplate(key: string) {
    setTemplateKey(key)
    if (key === 'custom') return
    const tpl = templates.find((t) => t.key === key)
    if (!tpl) return
    setName(tpl.label)
    setRegions(tpl.regions)
    setIntensity(tpl.intensity)
  }

  const today = isoDate(new Date())
  const isFuture = date > today
  // Shown for a future date, OR when editing a row that already carries one
  // of these event axes — whether it's planned or happened is solely a
  // factor of date, never of which template was picked.
  const showPlanning =
    isFuture || (editing && !!existing?.activity && (
      existing.activity.recurrence === 'weekly' ||
      !!existing.activity.event_end_date ||
      existing.activity.objective_id != null
    ))

  function activityFields() {
    const durationS = (num(hours) ?? 0) * 3600 + (num(minutes) ?? 0) * 60 || null
    return {
      name: name.trim(),
      template_key: templateKey,
      duration_s: durationS,
      regions,
      intensity,
      ...(isRouteCapable
        ? {
            distance: num(distance),
            elevation_gain: num(elevation),
            terrain,
            source: modeSource(routeMode),
            pack_weight: num(pack),
            bodyweight: num(body),
          }
        : {}),
      recurrence: (recurWeekly ? 'weekly' : 'none') as 'weekly' | 'none',
      event_end_date: !recurWeekly && eventEndDate ? eventEndDate : null,
      objective_id: objectiveId ? Number(objectiveId) : null,
    }
  }

  const create = useMutation({
    mutationFn: () =>
      api.logActivity({
        ...activityFields(),
        started_at: startedAtFor(date),
      }),
    onSuccess: (ws) => {
      if (isRouteCapable) {
        if (pack) localStorage.setItem(LAST_PACK, pack)
        if (body) localStorage.setItem(LAST_BODY, body)
      }
      qc.invalidateQueries({ queryKey: ['workouts'] })
      qc.invalidateQueries({ queryKey: ['calendar'] })
      setResult(ws)
      onSaved?.()
    },
  })

  const save = useMutation({
    mutationFn: () => {
      // Closing a row out (setting ended_at) happens automatically once its
      // date has arrived — never a separate status action — but only the
      // FIRST time (an already-closed row keeps its original completion
      // timestamp; a recurring template is never closed).
      const closeItOut =
        existing != null &&
        existing.ended_at == null &&
        !recurWeekly &&
        date <= today
      return api.updateWorkout(sessionId as number, {
        ...activityFields(),
        started_at: startedAtFor(date),
        ...(closeItOut ? { ended_at: new Date().toISOString() } : {}),
      })
    },
    onSuccess: (ws) => {
      if (isRouteCapable) {
        if (pack) localStorage.setItem(LAST_PACK, pack)
        if (body) localStorage.setItem(LAST_BODY, body)
      }
      qc.invalidateQueries({ queryKey: ['workouts'] })
      qc.invalidateQueries({ queryKey: ['calendar'] })
      qc.invalidateQueries({ queryKey: ['workout', sessionId] })
      setResult(ws)
      onSaved?.()
    },
  })

  const submit = editing ? save : create

  function reset() {
    setResult(null)
    submit.reset()
    onClose()
  }

  const canSubmit = name.trim().length > 0 && !submit.isPending

  return (
    <Sheet open={open} onClose={reset} title={editing ? 'Edit activity' : 'Add activity'}>
      {editing && loadingExisting ? (
        <Spinner />
      ) : result ? (
        <div className="space-y-4 text-center">
          <div className="text-5xl">{result.activity?.pack_weight_kg != null ? '🎒' : '🏃'}</div>
          <p className="text-slate-300">{result.name} {editing ? 'updated' : 'logged'}.</p>
          {result.activity?.metabolic_cost_kj != null && (
            <p className="text-lg font-semibold text-amber-400">
              {fmtLoad(result.activity.metabolic_cost_kj)} of load
            </p>
          )}
          <Button className="w-full" onClick={reset}>
            Done
          </Button>
        </div>
      ) : (
        <div className="space-y-4">
          <Field label="Date">
            <input
              className={inputCls}
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
            />
          </Field>

          {/* A dropdown, not a pill wall — the catalog is 20+ templates and
              still growing; scanning pills across seven rows beat the point
              of a quick-log form. Custom leads (it's the default). */}
          <Field label="Activity">
            {templates.length === 0 ? (
              <Spinner />
            ) : (
              <select
                className={inputCls}
                value={templateKey}
                onChange={(e) => pickTemplate(e.target.value)}
              >
                <option value="custom">Custom</option>
                {templates.map((t) => (
                  <option key={t.key} value={t.key}>
                    {t.label}
                  </option>
                ))}
              </select>
            )}
          </Field>

          <Field label="Name">
            <input
              className={inputCls}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Ultimate frisbee"
            />
          </Field>

          {showPlanning && (
            <div className="space-y-3 rounded-lg border border-fuchsia-800/40 bg-fuchsia-900/10 p-3">
              <label className="flex items-center gap-2 text-sm text-slate-300">
                <input
                  type="checkbox"
                  checked={recurWeekly}
                  onChange={(e) => setRecurWeekly(e.target.checked)}
                  className="h-4 w-4 accent-amber-500"
                />
                Repeats weekly
              </label>

              {!recurWeekly && (
                <Field label="Ends" hint="optional — last day of a multi-day trip">
                  <input
                    className={inputCls}
                    type="date"
                    value={eventEndDate}
                    min={date || undefined}
                    onChange={(e) => setEventEndDate(e.target.value)}
                  />
                </Field>
              )}

              <Field label="Anchor to objective" hint="optional — this IS the peak target">
                <select
                  className={inputCls}
                  value={objectiveId}
                  onChange={(e) => setObjectiveId(e.target.value)}
                >
                  <option value="">None</option>
                  {objectives.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.name}
                    </option>
                  ))}
                </select>
              </Field>

            </div>
          )}

          {isRouteCapable ? (
            <>
              <RouteCapture
                weightUnit={weight_unit}
                mode={routeMode}
                onModeChange={setRouteMode}
                distance={distance}
                onDistance={setDistance}
                elevation={elevation}
                onElevation={setElevation}
                hours={hours}
                onHours={setHours}
                minutes={minutes}
                onMinutes={setMinutes}
                terrain={terrain}
                onTerrain={setTerrain}
              />

              {/* Never required — most walks/runs get logged with no pack at all. */}
              <Field label={`Pack weight (${weight_unit}, optional)`}>
                <input
                  className={inputCls}
                  type="number"
                  inputMode="decimal"
                  value={pack}
                  onChange={(e) => setPack(e.target.value)}
                  placeholder="none"
                />
                <div className="mt-2 flex gap-2">
                  {packPresets.map((p) => (
                    <button
                      key={p}
                      type="button"
                      onClick={() => setPack(String(p))}
                      className="flex-1 rounded-lg bg-slate-800 py-1.5 text-sm text-slate-300 hover:bg-slate-700"
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </Field>

              {pack && (
                <Field label={`Bodyweight (${weight_unit})`}>
                  <input
                    className={inputCls}
                    type="number"
                    inputMode="decimal"
                    value={body}
                    onChange={(e) => setBody(e.target.value)}
                    placeholder="0"
                  />
                </Field>
              )}
            </>
          ) : (
            <Field label="Duration">
              <div className="flex items-center gap-2">
                <input
                  className={inputCls}
                  type="number"
                  inputMode="numeric"
                  value={hours}
                  onChange={(e) => setHours(e.target.value)}
                  placeholder="0"
                  aria-label="hours"
                />
                <span className="text-slate-400">h</span>
                <input
                  className={inputCls}
                  type="number"
                  inputMode="numeric"
                  value={minutes}
                  onChange={(e) => setMinutes(e.target.value)}
                  placeholder="0"
                  aria-label="minutes"
                />
                <span className="text-slate-400">m</span>
              </div>
            </Field>
          )}

          {/* Template-prefilled but always editable — a custom entry still needs a
              coarse estimate for the coach to reason about. */}
          <Field label="Body regions worked">
            <div className="flex flex-wrap gap-2">
              {REGIONS.map((r) => (
                <button
                  key={r.key}
                  type="button"
                  onClick={() => setRegions(r.key)}
                  className={`rounded-lg px-3 py-1.5 text-sm ${
                    regions === r.key
                      ? 'bg-amber-500 font-semibold text-slate-950'
                      : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                  }`}
                >
                  {r.label}
                </button>
              ))}
            </div>
          </Field>

          <Field label="Intensity">
            <div className="flex gap-2">
              {INTENSITIES.map((i) => (
                <button
                  key={i.key}
                  type="button"
                  onClick={() => setIntensity(i.key)}
                  className={`flex-1 rounded-lg py-1.5 text-sm ${
                    intensity === i.key
                      ? 'bg-amber-500 font-semibold text-slate-950'
                      : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                  }`}
                >
                  {i.label}
                </button>
              ))}
            </div>
          </Field>

          {isRouteCapable && (
            <p className="text-xs text-slate-500">
              Add a pack weight to see a load estimate — distance + time unlock it.
            </p>
          )}
          {submit.isError && (
            <p className="text-sm text-red-400">Couldn't save the activity. Try again.</p>
          )}
          <Button className="w-full" onClick={() => submit.mutate()} disabled={!canSubmit}>
            {submit.isPending ? 'Saving…' : editing ? 'Save' : isFuture ? 'Add activity' : 'Log activity'}
          </Button>
        </div>
      )}
    </Sheet>
  )
}
