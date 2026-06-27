import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
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

      <p className="mt-6 text-center text-xs text-slate-500">
        Vires · vires acquirit eundo
      </p>
    </div>
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
