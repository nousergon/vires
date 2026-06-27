import { useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type ExerciseBrief, type Template, type TemplateExerciseInput } from '../lib/api'
import { Button, Card, EmptyState, PageTitle, Sheet, Spinner } from '../components/ui'
import ExercisePicker from '../components/ExercisePicker'
import { useSettings } from '../lib/useSettings'

interface DraftRow extends TemplateExerciseInput {
  name: string
  is_timed: boolean
}

export default function TemplatesPage() {
  const qc = useQueryClient()
  const { data: templates = [], isLoading } = useQuery({
    queryKey: ['templates'],
    queryFn: api.listTemplates,
  })
  const [editing, setEditing] = useState<Template | 'new' | null>(null)

  const del = useMutation({
    mutationFn: (id: number) => api.deleteTemplate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['templates'] }),
  })

  return (
    <div>
      <PageTitle right={<Button onClick={() => setEditing('new')}>New</Button>}>Routines</PageTitle>

      {isLoading ? (
        <Spinner />
      ) : templates.length === 0 ? (
        <EmptyState title="No routines yet" hint="Create a reusable workout template." />
      ) : (
        <div className="space-y-2">
          {templates.map((t) => (
            <Card key={t.id} className="flex items-center justify-between">
              <button
                className="flex-1 text-left"
                onClick={async () => setEditing(await api.getTemplate(t.id))}
              >
                <div className="font-semibold text-slate-100">{t.name}</div>
                <div className="text-xs text-slate-400">{t.exercise_count} exercises</div>
              </button>
              <button
                className="px-2 text-sm text-red-400"
                onClick={() => confirm(`Delete "${t.name}"?`) && del.mutate(t.id)}
              >
                Delete
              </button>
            </Card>
          ))}
        </div>
      )}

      {editing && (
        <TemplateEditor
          initial={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ['templates'] })
            setEditing(null)
          }}
        />
      )}
    </div>
  )
}

function TemplateEditor({
  initial,
  onClose,
  onSaved,
}: {
  initial: Template | null
  onClose: () => void
  onSaved: () => void
}) {
  const [name, setName] = useState(initial?.name ?? '')
  const [rows, setRows] = useState<DraftRow[]>(
    initial?.exercises.map((te) => ({
      exercise_id: te.exercise.id,
      name: te.exercise.name,
      is_timed: te.exercise.is_timed,
      target_sets: te.target_sets,
      target_reps: te.target_reps,
      target_weight: te.target_weight,
      target_duration_seconds: te.target_duration_seconds,
      rest_seconds: te.rest_seconds,
    })) ?? [],
  )
  const [pickerOpen, setPickerOpen] = useState(false)
  const settings = useSettings()

  const save = useMutation({
    mutationFn: () => {
      const exercises: TemplateExerciseInput[] = rows.map((r) => ({
        exercise_id: r.exercise_id,
        target_sets: r.target_sets,
        target_reps: r.target_reps,
        target_weight: r.target_weight,
        target_duration_seconds: r.target_duration_seconds,
        rest_seconds: r.rest_seconds,
      }))
      return initial
        ? api.updateTemplate(initial.id, { name, exercises })
        : api.createTemplate({ name, exercises })
    },
    onSuccess: onSaved,
  })

  const addRow = (ex: ExerciseBrief) =>
    setRows((r) => [
      ...r,
      {
        exercise_id: ex.id,
        name: ex.name,
        is_timed: ex.is_timed,
        target_sets: settings.default_sets,
        target_reps: ex.is_timed ? null : settings.default_reps,
        target_weight: ex.is_timed ? null : defaultWeight(ex.equipment),
        target_duration_seconds: ex.is_timed ? 60 : null,
        rest_seconds: settings.default_rest_seconds,
      },
    ])
  const patch = (i: number, p: Partial<DraftRow>) =>
    setRows((r) => r.map((row, idx) => (idx === i ? { ...row, ...p } : row)))
  const removeRow = (i: number) => setRows((r) => r.filter((_, idx) => idx !== i))

  const numOrNull = (v: string) => (v === '' ? null : Number(v))

  return (
    <Sheet open onClose={onClose} title={initial ? 'Edit routine' : 'New routine'}>
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Routine name (e.g. Push Day)"
        className="w-full rounded-xl border border-slate-700 bg-slate-800 px-4 py-3 text-base outline-none focus:border-amber-500"
      />

      <div className="mt-4 space-y-2">
        {rows.map((r, i) => (
          <Card key={i} className="p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="font-medium">{r.name}</span>
              <button className="text-sm text-red-400" onClick={() => removeRow(i)}>
                remove
              </button>
            </div>
            <div className="grid grid-cols-4 gap-2 text-xs">
              <Field label="Sets">
                <NumInput value={r.target_sets} onChange={(v) => patch(i, { target_sets: numOrNull(v) })} />
              </Field>
              {r.is_timed ? (
                <Field label="Hold (s)">
                  <NumInput
                    value={r.target_duration_seconds}
                    onChange={(v) => patch(i, { target_duration_seconds: numOrNull(v) })}
                  />
                </Field>
              ) : (
                <>
                  <Field label="Reps">
                    <NumInput value={r.target_reps} onChange={(v) => patch(i, { target_reps: numOrNull(v) })} />
                  </Field>
                  <Field label={settings.weight_unit}>
                    <NumInput value={r.target_weight} onChange={(v) => patch(i, { target_weight: numOrNull(v) })} />
                  </Field>
                </>
              )}
              <Field label="Rest (s)">
                <NumInput value={r.rest_seconds} onChange={(v) => patch(i, { rest_seconds: numOrNull(v) })} />
              </Field>
            </div>
          </Card>
        ))}
      </div>

      <Button variant="secondary" className="mt-3 w-full" onClick={() => setPickerOpen(true)}>
        + Add exercise
      </Button>

      <Button
        className="mt-4 w-full"
        disabled={!name.trim() || save.isPending}
        onClick={() => save.mutate()}
      >
        {initial ? 'Save changes' : 'Create routine'}
      </Button>

      <ExercisePicker open={pickerOpen} onClose={() => setPickerOpen(false)} onSelect={addRow} />
    </Sheet>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-slate-400">{label}</span>
      {children}
    </label>
  )
}

function NumInput({ value, onChange }: { value: number | null | undefined; onChange: (v: string) => void }) {
  return (
    <input
      type="number"
      inputMode="numeric"
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value)}
      className="w-full rounded-lg bg-slate-800 px-2 py-2 text-center text-sm outline-none focus:ring-1 focus:ring-amber-500"
    />
  )
}

// Placeholder starting weight by equipment (lb). Just a sensible default to
// pre-fill — the user edits it, and the AI coach will propose it properly later.
// Bodyweight movements default to 0; unknown/user-created exercises stay blank.
function defaultWeight(equipment: string | null): number | null {
  const e = (equipment ?? '').toLowerCase()
  if (e === '') return null
  if (e.includes('body')) return 0
  if (e.includes('barbell')) return 45
  if (e.includes('kettlebell')) return 25
  if (e.includes('dumbbell')) return 15
  if (e.includes('plate') || e.includes('weight')) return 25
  if (e.includes('cable') || e.includes('machine')) return 30
  return null
}
