import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, type Terrain, type WorkoutSession } from '../lib/api'
import { useSettings } from '../lib/useSettings'
import { distanceUnit, elevationUnit, fmtLoad } from '../lib/units'
import { Button, Sheet } from './ui'

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

export default function RuckForm({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const { weight_unit } = useSettings()

  const [pack, setPack] = useState(() => localStorage.getItem(LAST_PACK) ?? '')
  const [body, setBody] = useState(() => localStorage.getItem(LAST_BODY) ?? '')
  const [distance, setDistance] = useState('')
  const [elevation, setElevation] = useState('')
  const [hours, setHours] = useState('')
  const [minutes, setMinutes] = useState('')
  const [terrain, setTerrain] = useState<Terrain>('trail')
  const [result, setResult] = useState<WorkoutSession | null>(null)

  const packPresets =
    weight_unit === 'kg' ? [10, 15, 20, 25] : [20, 30, 40, 50]

  const log = useMutation({
    mutationFn: () => {
      const durationS =
        (num(hours) ?? 0) * 3600 + (num(minutes) ?? 0) * 60 || null
      return api.logRuck({
        pack_weight: num(pack) ?? 0,
        bodyweight: num(body) ?? 0,
        distance: num(distance),
        elevation_gain: num(elevation),
        duration_s: durationS,
        terrain,
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
    setDistance('')
    setElevation('')
    setHours('')
    setMinutes('')
    log.reset()
    onClose()
  }

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
