import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type Settings, type Weekday, type WeightUnit } from '../lib/api'
import { authClient } from '../lib/authClient'
import { clearIdentityToken } from '../lib/identityToken'
import { useSettings } from '../lib/useSettings'
import { useAuth } from '../lib/useAuth'
import { requestNotificationPermission } from '../lib/timer'
import { ensurePushSubscription, disablePush } from '../lib/push'
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

      <Card className="mt-4 space-y-2">
        <h2 className="text-sm font-semibold text-slate-200">Training schedule</h2>
        <p className="text-xs text-slate-400">
          The coach defaults to these days when you don't name specific ones in a
          request — set once here instead of repeating it every conversation.
        </p>
        <WeekdayPicker
          selected={draft.preferred_weekdays}
          onChange={(v) => set('preferred_weekdays', v)}
        />
      </Card>

      <Card className="mt-4 space-y-1">
        <h2 className="mb-1 text-sm font-semibold text-slate-200">Timer alerts</h2>
        <p className="mb-2 text-xs text-slate-400">
          When a rest or hold timer ends. Keep-awake stops the screen sleeping mid-rest
          so the alert actually reaches you.
        </p>
        <Toggle
          label="Sound"
          on={draft.timer_sound}
          onChange={(v) => set('timer_sound', v)}
        />
        <Toggle
          label="Vibration"
          hint="Android only — iOS has no web vibration"
          on={draft.timer_vibration}
          onChange={(v) => set('timer_vibration', v)}
        />
        <Toggle
          label="Notification"
          hint="Locked-screen alerts (install to home screen on iOS)"
          on={draft.timer_notification}
          onChange={async (v) => {
            if (v) {
              if (!(await requestNotificationPermission())) return // blocked → stay off
              void ensurePushSubscription() // best-effort; falls back to foreground if unconfigured
            } else {
              void disablePush()
            }
            set('timer_notification', v)
          }}
        />
        <Toggle
          label="Keep screen awake during timers"
          on={draft.timer_keep_awake}
          onChange={(v) => set('timer_keep_awake', v)}
        />
      </Card>

      <Button className="mt-4 w-full" onClick={() => save.mutate()} disabled={save.isPending}>
        {saved ? 'Saved ✓' : 'Save settings'}
      </Button>

      <CalendarFeed />

      <Account />

      <p className="mt-6 text-center text-xs text-slate-500">
        Vires · vires acquirit eundo
      </p>
    </div>
  )
}

function Account() {
  const { me } = useAuth()
  const nav = useNavigate()
  const logout = useMutation({
    mutationFn: async () => {
      // Two sessions can coexist during the shared-identity transition
      // (vires-ops#60): the nousergon-auth cross-subdomain session and the
      // legacy vires_session cookie. Log out of both; signOut on an absent
      // shared session is an expected no-op (the legacy logout and token
      // purge below still run).
      await authClient.signOut().catch(() => {})
      await api.logout()
      clearIdentityToken()
    },
    onSuccess: () => nav('/login', { replace: true }),
  })

  if (!me) return null

  return (
    <Card className="mt-4 space-y-2">
      <h2 className="text-sm font-semibold text-slate-200">Account</h2>
      <p className="text-xs text-slate-400">
        Logged in as <span className="text-slate-200">{me.email}</span>
        {me.is_admin && ' · admin'}
      </p>
      <Button
        variant="secondary"
        className="w-full"
        disabled={logout.isPending}
        onClick={() => logout.mutate()}
      >
        Log out
      </Button>
    </Card>
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

const WEEKDAYS: { day: Weekday; label: string }[] = [
  { day: 'monday', label: 'M' },
  { day: 'tuesday', label: 'Tu' },
  { day: 'wednesday', label: 'W' },
  { day: 'thursday', label: 'Th' },
  { day: 'friday', label: 'F' },
  { day: 'saturday', label: 'Sa' },
  { day: 'sunday', label: 'Su' },
]

function WeekdayPicker({
  selected,
  onChange,
}: {
  selected: Weekday[]
  onChange: (v: Weekday[]) => void
}) {
  const toggle = (day: Weekday) =>
    onChange(selected.includes(day) ? selected.filter((d) => d !== day) : [...selected, day])

  return (
    <div className="flex gap-1.5">
      {WEEKDAYS.map(({ day, label }) => (
        <button
          key={day}
          type="button"
          onClick={() => toggle(day)}
          aria-pressed={selected.includes(day)}
          aria-label={day}
          className={`flex-1 rounded-lg py-2 text-xs font-semibold ${
            selected.includes(day)
              ? 'bg-amber-500 text-slate-950'
              : 'bg-slate-800 text-slate-300'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  )
}

function Toggle({
  label,
  hint,
  on,
  onChange,
}: {
  label: string
  hint?: string
  on: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!on)}
      className="flex w-full items-center justify-between py-2 text-left"
    >
      <span>
        <span className="block text-sm text-slate-200">{label}</span>
        {hint && <span className="block text-[11px] text-slate-500">{hint}</span>}
      </span>
      <span
        className={`relative h-6 w-11 shrink-0 rounded-full transition ${
          on ? 'bg-amber-500' : 'bg-slate-700'
        }`}
      >
        <span
          className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all ${
            on ? 'left-[1.375rem]' : 'left-0.5'
          }`}
        />
      </span>
    </button>
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
