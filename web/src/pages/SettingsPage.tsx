import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type Settings, type WeightUnit } from '../lib/api'
import { useSettings } from '../lib/useSettings'
import { Button, Card, PageTitle } from '../components/ui'

export default function SettingsPage() {
  const current = useSettings()
  const qc = useQueryClient()
  const [draft, setDraft] = useState<Settings>(current)
  const [saved, setSaved] = useState(false)

  // Sync local draft once settings load.
  useEffect(() => setDraft(current), [current])

  const save = useMutation({
    mutationFn: () => api.updateSettings(draft),
    onSuccess: (s) => {
      qc.setQueryData(['settings'], s)
      setSaved(true)
      setTimeout(() => setSaved(false), 1500)
    },
  })

  const set = <K extends keyof Settings>(k: K, v: Settings[K]) =>
    setDraft((d) => ({ ...d, [k]: v }))

  return (
    <div>
      <PageTitle>Settings</PageTitle>

      <Card className="space-y-5">
        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-300">Weight unit</label>
          <div className="flex gap-2">
            {(['lb', 'kg'] as WeightUnit[]).map((u) => (
              <button
                key={u}
                onClick={() => set('weight_unit', u)}
                className={`flex-1 rounded-xl py-2.5 text-sm font-semibold ${
                  draft.weight_unit === u
                    ? 'bg-amber-500 text-slate-950'
                    : 'bg-slate-800 text-slate-300'
                }`}
              >
                {u.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        <NumberField
          label="Default rest timer (seconds)"
          value={draft.default_rest_seconds}
          onChange={(v) => set('default_rest_seconds', v)}
        />
        <div className="grid grid-cols-2 gap-3">
          <NumberField
            label="Default sets"
            value={draft.default_sets}
            onChange={(v) => set('default_sets', v)}
          />
          <NumberField
            label="Default reps"
            value={draft.default_reps}
            onChange={(v) => set('default_reps', v)}
          />
        </div>
      </Card>

      <Button className="mt-4 w-full" onClick={() => save.mutate()} disabled={save.isPending}>
        {saved ? 'Saved ✓' : 'Save settings'}
      </Button>

      <CalendarFeed />

      <p className="mt-6 text-center text-xs text-slate-500">
        Vires · vires acquirit eundo
      </p>
    </div>
  )
}

function CalendarFeed() {
  const qc = useQueryClient()
  const [copied, setCopied] = useState(false)
  const { data: feed } = useQuery({ queryKey: ['feed-url'], queryFn: api.feedUrl })
  const rotate = useMutation({
    mutationFn: api.rotateFeedUrl,
    onSuccess: (f) => qc.setQueryData(['feed-url'], f),
  })

  if (!feed) return null
  const httpsUrl = `${window.location.origin}${feed.ics_path}`
  const webcalUrl = httpsUrl.replace(/^https?:/, 'webcal:')

  async function copy() {
    await navigator.clipboard.writeText(httpsUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <Card className="mt-6 space-y-3">
      <div>
        <h2 className="text-sm font-semibold text-slate-200">Calendar feed</h2>
        <p className="mt-1 text-xs text-slate-400">
          Subscribe in Google or Apple Calendar to overlay your planned + completed
          workouts (read-only; Google refreshes every few hours).
        </p>
      </div>

      <div className="flex items-center gap-2 rounded-lg bg-slate-800 px-3 py-2">
        <span className="flex-1 truncate text-xs text-slate-400">{httpsUrl}</span>
        <button className="text-xs font-semibold text-amber-400" onClick={copy}>
          {copied ? 'Copied ✓' : 'Copy'}
        </button>
      </div>

      <div className="flex gap-2">
        <a
          href={webcalUrl}
          className="flex-1 rounded-xl bg-slate-800 py-2.5 text-center text-sm font-semibold text-slate-100 hover:bg-slate-700"
        >
          Add to calendar
        </a>
        <button
          className="rounded-xl border border-slate-700 px-3 py-2.5 text-sm text-slate-400 hover:bg-slate-800"
          onClick={() => {
            if (confirm('Rotate the feed link? Existing subscriptions will stop updating.'))
              rotate.mutate()
          }}
        >
          Reset link
        </button>
      </div>
    </Card>
  )
}

function NumberField({
  label,
  value,
  onChange,
}: {
  label: string
  value: number
  onChange: (v: number) => void
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-slate-300">{label}</span>
      <input
        type="number"
        inputMode="numeric"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full rounded-xl border border-slate-700 bg-slate-800 px-4 py-2.5 outline-none focus:border-amber-500"
      />
    </label>
  )
}
