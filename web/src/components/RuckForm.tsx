import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  api,
  type RoutePoint,
  type RouteStats,
  type RuckSource,
  type Terrain,
  type WorkoutSession,
} from '../lib/api'
import { useSettings } from '../lib/useSettings'
import { distanceUnit, elevationUnit, fmtLoad, metersToDistance, metersToElevation } from '../lib/units'
import { Button, Sheet } from './ui'
import RouteDrawMap from './RouteDrawMap'

// Pack weight + bodyweight are remembered so the highest-friction inputs become
// one tap ("same as last") on the next ruck — the load number is the only thing
// no device can supply, so we make entering it cheap.
const LAST_PACK = 'vires.ruck.lastPack'
const LAST_BODY = 'vires.ruck.lastBody'

const TERRAINS: { key: Terrain; label: string }[] = [
  { key: 'road', label: 'Road' },
  { key: 'trail', label: 'Trail' },
  { key: 'offtrail', label: 'Off-trail' },
  { key: 'snow', label: 'Snow' },
]

// The three flexible input modes. All populate the same editable fields below and
// funnel through one log call, tagged with the corresponding source.
type Mode = 'manual' | 'trail' | 'draw' | 'gpx'
const MODES: { key: Mode; label: string; source: RuckSource }[] = [
  { key: 'manual', label: 'Manual', source: 'manual' },
  { key: 'trail', label: 'Search', source: 'route_search' },
  { key: 'draw', label: 'Draw', source: 'route_draw' },
  { key: 'gpx', label: 'GPX', source: 'gpx' },
]

const inputCls =
  'w-full rounded-xl border border-slate-700 bg-slate-800 px-4 py-2.5 text-base outline-none focus:border-amber-500'

function num(v: string): number | null {
  const n = parseFloat(v)
  return Number.isFinite(n) ? n : null
}

function round(n: number, dp: number): number {
  const f = 10 ** dp
  return Math.round(n * f) / f
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

export default function RuckForm({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const { weight_unit } = useSettings()

  const [mode, setMode] = useState<Mode>('manual')
  const [pack, setPack] = useState(() => localStorage.getItem(LAST_PACK) ?? '')
  const [body, setBody] = useState(() => localStorage.getItem(LAST_BODY) ?? '')
  const [distance, setDistance] = useState('')
  const [elevation, setElevation] = useState('')
  const [hours, setHours] = useState('')
  const [minutes, setMinutes] = useState('')
  const [terrain, setTerrain] = useState<Terrain>('trail')
  const [query, setQuery] = useState('')
  const [drawPoints, setDrawPoints] = useState<RoutePoint[]>([])
  const [result, setResult] = useState<WorkoutSession | null>(null)

  const packPresets = weight_unit === 'kg' ? [10, 15, 20, 25] : [20, 30, 40, 50]

  // Any derived mode lands its SI stats into the same editable display fields.
  function applyStats(s: RouteStats) {
    setDistance(String(round(metersToDistance(s.distance_m, weight_unit), 2)))
    if (s.elevation_gain_m != null) {
      setElevation(String(Math.round(metersToElevation(s.elevation_gain_m, weight_unit))))
    }
    if (s.duration_s != null) {
      setHours(String(Math.floor(s.duration_s / 3600)))
      setMinutes(String(Math.round((s.duration_s % 3600) / 60)))
    }
  }

  const search = useMutation({ mutationFn: (q: string) => api.searchTrails(q) })
  const measure = useMutation({
    mutationFn: (pts: { lat: number; lon: number }[]) => api.measureRoute(pts),
    onSuccess: applyStats,
  })
  const gpx = useMutation({
    mutationFn: (text: string) => api.importGpx(text),
    onSuccess: applyStats,
  })

  const log = useMutation({
    mutationFn: () => {
      const durationS = (num(hours) ?? 0) * 3600 + (num(minutes) ?? 0) * 60 || null
      const source = MODES.find((m) => m.key === mode)!.source
      return api.logRuck({
        pack_weight: num(pack) ?? 0,
        bodyweight: num(body) ?? 0,
        distance: num(distance),
        elevation_gain: num(elevation),
        duration_s: durationS,
        terrain,
        source,
      })
    },
    onSuccess: (ws) => {
      localStorage.setItem(LAST_PACK, pack)
      localStorage.setItem(LAST_BODY, body)
      qc.invalidateQueries({ queryKey: ['workouts'] })
      qc.invalidateQueries({ queryKey: ['calendar'] })
      setResult(ws)
    },
  })

  function reset() {
    setResult(null)
    setMode('manual')
    setDistance('')
    setElevation('')
    setHours('')
    setMinutes('')
    setQuery('')
    setDrawPoints([])
    search.reset()
    measure.reset()
    gpx.reset()
    log.reset()
    onClose()
  }

  async function onGpxFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (f) gpx.mutate(await f.text())
  }

  const candidates = search.data?.candidates ?? []
  const canSubmit = (num(pack) ?? 0) > 0 && (num(body) ?? 0) > 0 && !log.isPending

  return (
    <Sheet open={open} onClose={reset} title="Log a ruck">
      {result ? (
        <div className="space-y-4 text-center">
          <div className="text-5xl">🎒</div>
          <p className="text-slate-300">Ruck logged.</p>
          {result.ruck?.metabolic_cost_kj != null ? (
            <p className="text-lg font-semibold text-amber-400">
              {fmtLoad(result.ruck.metabolic_cost_kj)} of load
            </p>
          ) : (
            <p className="text-sm text-slate-400">
              Add distance + time next time to see the load estimate.
            </p>
          )}
          <Button className="w-full" onClick={reset}>
            Done
          </Button>
        </div>
      ) : (
        <div className="space-y-4">
          <Field label={`Pack weight (${weight_unit})`}>
            <input
              className={inputCls}
              type="number"
              inputMode="decimal"
              value={pack}
              onChange={(e) => setPack(e.target.value)}
              placeholder="0"
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

          {/* How to fill distance/elevation: type it, find a trail, or import a GPX. */}
          <Field label="Route">
            <div className="mb-2 flex rounded-xl bg-slate-800 p-1 text-sm">
              {MODES.map((m) => (
                <button
                  key={m.key}
                  type="button"
                  onClick={() => setMode(m.key)}
                  className={`flex-1 rounded-lg py-1.5 transition ${
                    mode === m.key ? 'bg-slate-700 text-amber-400' : 'text-slate-400'
                  }`}
                >
                  {m.label}
                </button>
              ))}
            </div>

            {mode === 'trail' && (
              <div className="space-y-2">
                <div className="flex gap-2">
                  <input
                    className={inputCls}
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="e.g. Mailbox Peak Trail"
                    aria-label="trail name"
                  />
                  <Button
                    variant="secondary"
                    onClick={() => query.trim().length >= 3 && search.mutate(query.trim())}
                    disabled={search.isPending || query.trim().length < 3}
                  >
                    {search.isPending ? '…' : 'Find'}
                  </Button>
                </div>
                {search.isSuccess && candidates.length === 0 && (
                  <p className="text-xs text-slate-500">
                    No matching trails found — draw isn't available yet, so enter distance + elevation manually below.
                  </p>
                )}
                {candidates.map((c) => (
                  <button
                    key={c.osm_id}
                    type="button"
                    onClick={() => measure.mutate(c.points)}
                    className="block w-full rounded-lg bg-slate-800 px-3 py-2 text-left text-sm hover:bg-slate-700"
                  >
                    <span className="font-medium text-slate-100">{c.name}</span>
                    <span className="ml-2 text-slate-400">
                      {round(metersToDistance(c.distance_m, weight_unit), 1)} {distanceUnit(weight_unit)}
                    </span>
                  </button>
                ))}
                {measure.isPending && <p className="text-xs text-slate-400">Measuring route…</p>}
              </div>
            )}

            {mode === 'draw' && (
              <div className="space-y-2">
                <p className="text-xs text-slate-500">
                  Tap the map to trace your route, then measure it.
                </p>
                <RouteDrawMap
                  points={drawPoints}
                  onAddPoint={(lat, lon) => setDrawPoints((p) => [...p, { lat, lon }])}
                />
                <div className="flex gap-2">
                  <Button
                    variant="secondary"
                    className="flex-1"
                    onClick={() => measure.mutate(drawPoints)}
                    disabled={drawPoints.length < 2 || measure.isPending}
                  >
                    {measure.isPending ? 'Measuring…' : `Measure route (${drawPoints.length} pts)`}
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => setDrawPoints((p) => p.slice(0, -1))}
                    disabled={drawPoints.length === 0}
                  >
                    Undo
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => setDrawPoints([])}
                    disabled={drawPoints.length === 0}
                  >
                    Clear
                  </Button>
                </div>
              </div>
            )}

            {mode === 'gpx' && (
              <div className="space-y-2">
                <input
                  type="file"
                  accept=".gpx,application/gpx+xml,text/xml"
                  onChange={onGpxFile}
                  className="block w-full text-sm text-slate-300 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-700 file:px-3 file:py-2 file:text-slate-100"
                  aria-label="gpx file"
                />
                {gpx.isPending && <p className="text-xs text-slate-400">Reading track…</p>}
                {gpx.isError && (
                  <p className="text-xs text-red-400">Couldn't read that GPX — enter values manually.</p>
                )}
              </div>
            )}

            {mode !== 'manual' && (
              <p className="mt-2 text-xs text-slate-500">
                Auto-filled below — edit anything that looks off.
              </p>
            )}
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label={`Distance (${distanceUnit(weight_unit)})`}>
              <input
                className={inputCls}
                type="number"
                inputMode="decimal"
                value={distance}
                onChange={(e) => setDistance(e.target.value)}
                placeholder="—"
              />
            </Field>
            <Field label={`Elevation gain (${elevationUnit(weight_unit)})`}>
              <input
                className={inputCls}
                type="number"
                inputMode="decimal"
                value={elevation}
                onChange={(e) => setElevation(e.target.value)}
                placeholder="—"
              />
            </Field>
          </div>

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

          <Field label="Terrain">
            <div className="flex gap-2">
              {TERRAINS.map((t) => (
                <button
                  key={t.key}
                  type="button"
                  onClick={() => setTerrain(t.key)}
                  className={`flex-1 rounded-lg py-1.5 text-sm ${
                    terrain === t.key
                      ? 'bg-amber-500 font-semibold text-slate-950'
                      : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </Field>

          <p className="text-xs text-slate-500">
            Distance + time unlock the pack-weight-adjusted load estimate.
          </p>
          {log.isError && (
            <p className="text-sm text-red-400">Couldn't log the ruck. Try again.</p>
          )}
          <Button className="w-full" onClick={() => log.mutate()} disabled={!canSubmit}>
            {log.isPending ? 'Logging…' : 'Log ruck'}
          </Button>
        </div>
      )}
    </Sheet>
  )
}
