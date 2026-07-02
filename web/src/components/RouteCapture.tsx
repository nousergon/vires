import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api, type RoutePoint, type RouteStats, type Terrain, type WeightUnit } from '../lib/api'
import { distanceUnit, elevationUnit, metersToDistance, metersToElevation } from '../lib/units'
import { ROUTE_MODES, type RouteMode } from '../lib/routeMode'
import { Button } from './ui'
import RouteDrawMap from './RouteDrawMap'

const TERRAINS: { key: Terrain; label: string }[] = [
  { key: 'road', label: 'Road' },
  { key: 'trail', label: 'Trail' },
  { key: 'offtrail', label: 'Off-trail' },
  { key: 'snow', label: 'Snow' },
]

const inputCls =
  'w-full rounded-xl border border-slate-700 bg-slate-800 px-4 py-2.5 text-base outline-none focus:border-amber-500'

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

export default function RouteCapture({
  weightUnit,
  mode,
  onModeChange,
  distance,
  onDistance,
  elevation,
  onElevation,
  hours,
  onHours,
  minutes,
  onMinutes,
  terrain,
  onTerrain,
}: {
  weightUnit: WeightUnit
  mode: RouteMode
  onModeChange: (m: RouteMode) => void
  distance: string
  onDistance: (v: string) => void
  elevation: string
  onElevation: (v: string) => void
  hours: string
  onHours: (v: string) => void
  minutes: string
  onMinutes: (v: string) => void
  terrain: Terrain
  onTerrain: (t: Terrain) => void
}) {
  const [query, setQuery] = useState('')
  const [drawPoints, setDrawPoints] = useState<RoutePoint[]>([])

  // Any derived mode lands its SI stats into the same editable display fields.
  function applyStats(s: RouteStats) {
    onDistance(String(round(metersToDistance(s.distance_m, weightUnit), 2)))
    if (s.elevation_gain_m != null) {
      onElevation(String(Math.round(metersToElevation(s.elevation_gain_m, weightUnit))))
    }
    if (s.duration_s != null) {
      onHours(String(Math.floor(s.duration_s / 3600)))
      onMinutes(String(Math.round((s.duration_s % 3600) / 60)))
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

  async function onGpxFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (f) gpx.mutate(await f.text())
  }

  const candidates = search.data?.candidates ?? []

  return (
    <>
      {/* How to fill distance/elevation: type it, find a trail, or import a GPX. */}
      <Field label="Route">
        <div className="mb-2 flex rounded-xl bg-slate-800 p-1 text-sm">
          {ROUTE_MODES.map((m) => (
            <button
              key={m.key}
              type="button"
              onClick={() => onModeChange(m.key)}
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
                  {round(metersToDistance(c.distance_m, weightUnit), 1)} {distanceUnit(weightUnit)}
                </span>
              </button>
            ))}
            {measure.isPending && <p className="text-xs text-slate-400">Measuring route…</p>}
          </div>
        )}

        {mode === 'draw' && (
          <div className="space-y-2">
            <p className="text-xs text-slate-500">Tap the map to trace your route, then measure it.</p>
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
          <p className="mt-2 text-xs text-slate-500">Auto-filled below — edit anything that looks off.</p>
        )}
      </Field>

      <div className="grid grid-cols-2 gap-3">
        <Field label={`Distance (${distanceUnit(weightUnit)})`}>
          <input
            className={inputCls}
            type="number"
            inputMode="decimal"
            value={distance}
            onChange={(e) => onDistance(e.target.value)}
            placeholder="—"
          />
        </Field>
        <Field label={`Elevation gain (${elevationUnit(weightUnit)})`}>
          <input
            className={inputCls}
            type="number"
            inputMode="decimal"
            value={elevation}
            onChange={(e) => onElevation(e.target.value)}
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
            onChange={(e) => onHours(e.target.value)}
            placeholder="0"
            aria-label="hours"
          />
          <span className="text-slate-400">h</span>
          <input
            className={inputCls}
            type="number"
            inputMode="numeric"
            value={minutes}
            onChange={(e) => onMinutes(e.target.value)}
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
              onClick={() => onTerrain(t.key)}
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
    </>
  )
}
