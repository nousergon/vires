import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type LoadIntensity, type LoadRegions, type Terrain, type WorkoutSession } from '../lib/api'
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

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-400">
        {label}
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
  onClose,
}: {
  open: boolean
  // Seed the log date (e.g. the tapped Plan-calendar day). Omit for "today".
  defaultDate?: string | null
  onClose: () => void
}) {
  const qc = useQueryClient()
  const { weight_unit } = useSettings()

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
  const [result, setResult] = useState<WorkoutSession | null>(null)

  const packPresets = weight_unit === 'kg' ? [10, 15, 20, 25] : [20, 30, 40, 50]

  // Re-seed the date whenever the sheet (re)opens with a new default — the
  // sheet stays mounted while hidden, so a mount-time useState initializer
  // alone wouldn't pick up a changed defaultDate on reopen.
  useEffect(() => {
    if (!open) return
    setDate(defaultDate ?? isoDate(new Date()))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, defaultDate])

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

  const log = useMutation({
    mutationFn: () => {
      const durationS = (num(hours) ?? 0) * 3600 + (num(minutes) ?? 0) * 60 || null
      return api.logActivity({
        name: name.trim(),
        template_key: templateKey,
        duration_s: durationS,
        regions,
        intensity,
        started_at: startedAtFor(date),
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
      })
    },
    onSuccess: (ws) => {
      // Only persist pack/bodyweight when this log actually used them — an
      // unrelated custom entry shouldn't blank out a remembered pack weight.
      if (isRouteCapable) {
        if (pack) localStorage.setItem(LAST_PACK, pack)
        if (body) localStorage.setItem(LAST_BODY, body)
      }
      qc.invalidateQueries({ queryKey: ['workouts'] })
      qc.invalidateQueries({ queryKey: ['calendar'] })
      setResult(ws)
    },
  })

  function reset() {
    setResult(null)
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
    log.reset()
    onClose()
  }

  const canSubmit = name.trim().length > 0 && !log.isPending

  return (
    <Sheet open={open} onClose={reset} title="Log an activity">
      {result ? (
        <div className="space-y-4 text-center">
          <div className="text-5xl">{result.activity?.pack_weight_kg != null ? '🎒' : '🏃'}</div>
          <p className="text-slate-300">{result.name} logged.</p>
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
              max={isoDate(new Date())}
              onChange={(e) => setDate(e.target.value)}
            />
          </Field>

          <Field label="Activity">
            {templates.length === 0 ? (
              <Spinner />
            ) : (
              <div className="flex flex-wrap gap-2">
                {templates.map((t) => (
                  <button
                    key={t.key}
                    type="button"
                    onClick={() => pickTemplate(t.key)}
                    className={`rounded-full border px-3 py-1.5 text-sm ${
                      templateKey === t.key
                        ? 'border-amber-600/60 bg-amber-900/30 text-amber-200'
                        : 'border-slate-700 text-slate-300 hover:bg-slate-800'
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => pickTemplate('custom')}
                  className={`rounded-full border px-3 py-1.5 text-sm ${
                    templateKey === 'custom'
                      ? 'border-amber-600/60 bg-amber-900/30 text-amber-200'
                      : 'border-slate-700 text-slate-300 hover:bg-slate-800'
                  }`}
                >
                  Custom
                </button>
              </div>
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
          {log.isError && (
            <p className="text-sm text-red-400">Couldn't log the activity. Try again.</p>
          )}
          <Button className="w-full" onClick={() => log.mutate()} disabled={!canSubmit}>
            {log.isPending ? 'Logging…' : 'Log activity'}
          </Button>
        </div>
      )}
    </Sheet>
  )
}
