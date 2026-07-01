import { type ReactNode, useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { Button, Sheet, Spinner } from './ui'

const EVENT_TYPES = ['competition', 'league', 'recreation', 'travel', 'rehab'] as const
const LOAD_REGIONS = ['legs', 'upper', 'full', 'core', 'none'] as const
const LOAD_INTENSITIES = ['light', 'moderate', 'hard'] as const

/**
 * Create a new athletic-calendar CalendarEvent or edit an existing one (by
 * ``eventId``). A CalendarEvent is a training-load CONSTRAINT the coach trains
 * *around* — a race, a weekly league game, a trip, a rehab window — distinct
 * from an Objective, which is a goal the coach peaks *toward*
 * (see vires-ops#30/#31/#32). Saving with no ``eventId`` always POSTs a NEW event.
 */
export default function CalendarEventSheet({
  open,
  eventId,
  defaultDate,
  onClose,
  onSaved,
}: {
  open: boolean
  // The event to edit; omit / null to create a brand-new one.
  eventId?: number | null
  // Seed event_date for a new event (e.g. the tapped calendar day).
  defaultDate?: string | null
  onClose: () => void
  onSaved: () => void
}) {
  const qc = useQueryClient()
  const { data: all = [], isLoading } = useQuery({
    queryKey: ['calendar-events'],
    queryFn: api.listCalendarEvents,
    enabled: open,
  })

  const editing = eventId != null ? (all.find((e) => e.id === eventId) ?? null) : null

  const [name, setName] = useState('')
  const [sport, setSport] = useState('')
  const [type, setType] = useState<(typeof EVENT_TYPES)[number]>('competition')
  const [eventDate, setEventDate] = useState('')
  const [eventEndDate, setEventEndDate] = useState('')
  const [recurWeekly, setRecurWeekly] = useState(false)
  const [tagLoad, setTagLoad] = useState(false)
  const [regions, setRegions] = useState<(typeof LOAD_REGIONS)[number]>('full')
  const [intensity, setIntensity] = useState<(typeof LOAD_INTENSITIES)[number]>('moderate')
  const [durationMin, setDurationMin] = useState('')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)

  // Seed the form when the sheet opens / the edited event changes.
  useEffect(() => {
    if (!open) return
    setError(null)
    setName(editing?.name ?? '')
    setSport(editing?.sport ?? '')
    setType(editing?.type ?? 'competition')
    setEventDate(editing?.event_date ?? defaultDate ?? '')
    setEventEndDate(editing?.event_end_date ?? '')
    setRecurWeekly((editing?.recurrence ?? 'none') === 'weekly')
    setTagLoad(!!editing?.load)
    setRegions(editing?.load?.regions ?? 'full')
    setIntensity(editing?.load?.intensity ?? 'moderate')
    setDurationMin(editing?.load?.duration_min != null ? String(editing.load.duration_min) : '')
    setNotes(editing?.notes ?? '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, editing?.id])

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['calendar-events'] })
    qc.invalidateQueries({ queryKey: ['calendar-events-window'] })
  }

  const saveEvent = useMutation({
    mutationFn: async () => {
      const body = {
        name: name.trim(),
        sport: sport.trim() || null,
        type,
        event_date: eventDate,
        event_end_date: !recurWeekly && eventEndDate ? eventEndDate : null,
        recurrence: recurWeekly ? ('weekly' as const) : ('none' as const),
        load: tagLoad
          ? {
              regions,
              intensity,
              duration_min: durationMin ? Number(durationMin) : null,
            }
          : null,
        notes: notes.trim() || null,
      }
      return editing ? api.updateCalendarEvent(editing.id, body) : api.createCalendarEvent(body)
    },
    onSuccess: () => {
      refresh()
      onSaved()
    },
    onError: (e) => setError((e as Error).message.replace(/^\d+:\s*/, '')),
  })

  const deleteEvent = useMutation({
    mutationFn: async () => {
      if (!editing) return
      await api.deleteCalendarEvent(editing.id)
    },
    onSuccess: () => {
      refresh()
      onSaved()
      onClose()
    },
  })

  const eventEndInvalid = !!eventEndDate && !!eventDate && eventEndDate < eventDate
  const canSave = !!name.trim() && !!eventDate && !eventEndInvalid && !saveEvent.isPending

  return (
    <Sheet open={open} onClose={onClose} title={editing ? '📅 Edit event' : '📅 New event'}>
      {isLoading ? (
        <Spinner />
      ) : (
        <div className="space-y-5">
          <div className="space-y-3">
            <Field label="Event">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Tuesday league game"
                className="input"
              />
            </Field>

            <Field label="Type">
              <select
                value={type}
                onChange={(e) => setType(e.target.value as (typeof EVENT_TYPES)[number])}
                className="input"
              >
                {EVENT_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Sport" hint="drives the needs-analysis (alpine is authored)">
              <input
                value={sport}
                onChange={(e) => setSport(e.target.value)}
                placeholder="alpine"
                className="input"
              />
            </Field>

            <Field label="Date">
              <input
                type="date"
                value={eventDate}
                onChange={(e) => setEventDate(e.target.value)}
                className="input"
              />
            </Field>

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
              <Field
                label="Ends"
                hint="optional — last day of a multi-day event (e.g. a trip)"
              >
                <input
                  type="date"
                  value={eventEndDate}
                  min={eventDate || undefined}
                  onChange={(e) => setEventEndDate(e.target.value)}
                  className="input"
                />
              </Field>
            )}

            <label className="flex items-center gap-2 text-sm text-slate-300">
              <input
                type="checkbox"
                checked={tagLoad}
                onChange={(e) => setTagLoad(e.target.checked)}
                className="h-4 w-4 accent-amber-500"
              />
              Tag training load
            </label>

            {tagLoad && (
              <div className="space-y-3 rounded-lg border border-slate-800 bg-slate-800/40 p-3">
                <Field label="Regions">
                  <select
                    value={regions}
                    onChange={(e) => setRegions(e.target.value as (typeof LOAD_REGIONS)[number])}
                    className="input"
                  >
                    {LOAD_REGIONS.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Intensity">
                  <select
                    value={intensity}
                    onChange={(e) =>
                      setIntensity(e.target.value as (typeof LOAD_INTENSITIES)[number])
                    }
                    className="input"
                  >
                    {LOAD_INTENSITIES.map((i) => (
                      <option key={i} value={i}>
                        {i}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Duration" hint="minutes, optional">
                  <input
                    type="number"
                    min={1}
                    value={durationMin}
                    onChange={(e) => setDurationMin(e.target.value)}
                    placeholder="e.g. 90"
                    className="input"
                  />
                </Field>
              </div>
            )}

            <Field label="Notes" hint="optional">
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={2}
                className="input"
              />
            </Field>

            {error && (
              <p className="rounded-lg border border-red-800/50 bg-red-900/20 px-3 py-2 text-sm text-red-300">
                {error}
              </p>
            )}

            <Button className="w-full" onClick={() => saveEvent.mutate()} disabled={!canSave}>
              {saveEvent.isPending ? 'Saving…' : editing ? 'Update event' : 'Add event'}
            </Button>

            {editing && (
              <Button
                variant="danger"
                className="w-full"
                onClick={() => deleteEvent.mutate()}
                disabled={deleteEvent.isPending}
              >
                {deleteEvent.isPending ? 'Deleting…' : 'Delete event'}
              </Button>
            )}
          </div>

          <p className="text-xs text-slate-500">
            Events are constraints the coach trains around (races, leagues, trips, rehab) — not
            goals it peaks toward. Set a goal from the Objectives section above instead.
          </p>
        </div>
      )}
    </Sheet>
  )
}

// --------------------------------------------------------------------------- //
function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: ReactNode
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
        {hint && <span className="ml-2 normal-case font-normal text-slate-600">{hint}</span>}
      </span>
      {children}
    </label>
  )
}
