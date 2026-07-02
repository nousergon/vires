import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type LoadIntensity, type LoadRegions, type WorkoutSession } from '../lib/api'
import { isoDate } from '../lib/calendar'
import { Button, Sheet, Spinner } from './ui'

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

// Keeps today's time-of-day but takes on the chosen day (mirrors RuckForm —
// there's no real start/stop capture in Tier 0).
function startedAtFor(dateStr: string): string {
  const [y, m, d] = dateStr.split('-').map(Number)
  const now = new Date()
  return new Date(y, m - 1, d, now.getHours(), now.getMinutes(), now.getSeconds()).toISOString()
}

export default function ActivityForm({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient()

  const [date, setDate] = useState(() => isoDate(new Date()))
  const [templateKey, setTemplateKey] = useState('custom')
  const [name, setName] = useState('')
  const [regions, setRegions] = useState<LoadRegions>('full')
  const [intensity, setIntensity] = useState<LoadIntensity>('moderate')
  const [hours, setHours] = useState('')
  const [minutes, setMinutes] = useState('')
  const [result, setResult] = useState<WorkoutSession | null>(null)

  const { data: templates = [] } = useQuery({
    queryKey: ['activity-templates'],
    queryFn: api.listActivityTemplates,
  })

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
      })
    },
    onSuccess: (ws) => {
      qc.invalidateQueries({ queryKey: ['workouts'] })
      qc.invalidateQueries({ queryKey: ['calendar'] })
      setResult(ws)
    },
  })

  function reset() {
    setResult(null)
    setDate(isoDate(new Date()))
    setTemplateKey('custom')
    setName('')
    setRegions('full')
    setIntensity('moderate')
    setHours('')
    setMinutes('')
    log.reset()
    onClose()
  }

  const canSubmit = name.trim().length > 0 && !log.isPending

  return (
    <Sheet open={open} onClose={reset} title="Log an activity">
      {result ? (
        <div className="space-y-4 text-center">
          <div className="text-5xl">🏃</div>
          <p className="text-slate-300">{result.name} logged.</p>
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
