import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderWithProviders } from '../test/utils'
import CoachSheet from './CoachSheet'
import { api, type ProgramPreview } from '../lib/api'

beforeEach(() => vi.restoreAllMocks())

const PREVIEW: ProgramPreview = {
  name: 'Test Block',
  coach_summary: 'A 4-week ramp from 10 to 4 reps.',
  start_date: '2026-06-29',
  end_date: '2026-07-20',
  weight_unit: 'lb',
  spec: {
    name: 'Test Block',
    start_date: '2026-06-29',
    duration_weeks: 4,
    new_routines: [],
    schedule: [{ template_id: 1, weekday: 'monday' }],
    progressions: [],
    deload_weeks: [],
    coach_summary: 'A 4-week ramp from 10 to 4 reps.',
  },
  created_routines: [],
  planned_workouts: [
    {
      template_id: 1,
      scheduled_date: '2026-06-29',
      name: 'Upper — Week 1',
      week_index: 1,
      exercises: [
        {
          exercise_id: 1,
          exercise_name: 'Bench',
          order_index: 0,
          target_sets: 3,
          target_reps: 10,
          target_weight: 135,
          target_duration_seconds: null,
          rest_seconds: null,
          notes: null,
        },
      ],
    },
  ],
}

describe('CoachSheet', () => {
  it('generates a plan, previews it, and confirms', async () => {
    vi.spyOn(api, 'coachGenerate').mockResolvedValue(PREVIEW)
    const save = vi.spyOn(api, 'coachSaveProgram').mockResolvedValue({ id: 7, name: 'Test Block' })
    const onSaved = vi.fn()
    renderWithProviders(<CoachSheet open onClose={() => {}} onSaved={onSaved} />)

    fireEvent.change(screen.getByPlaceholderText(/Run both my routines/i), {
      target: { value: 'two routines, 4 weeks' },
    })
    fireEvent.click(screen.getByText('Generate plan'))

    expect(await screen.findByText('A 4-week ramp from 10 to 4 reps.')).toBeInTheDocument()
    expect(screen.getByText('Upper — Week 1')).toBeInTheDocument()
    expect(screen.getByText(/Bench · 3×10 @ 135lb/)).toBeInTheDocument()

    fireEvent.click(screen.getByText('Add to calendar'))
    await waitFor(() => expect(save).toHaveBeenCalled())
    await waitFor(() => expect(onSaved).toHaveBeenCalled())
  })

  it('surfaces a friendly error when the coach is unavailable', async () => {
    vi.spyOn(api, 'coachGenerate').mockRejectedValue(new Error('503: not configured'))
    renderWithProviders(<CoachSheet open onClose={() => {}} onSaved={() => {}} />)
    fireEvent.change(screen.getByPlaceholderText(/Run both my routines/i), {
      target: { value: 'plan me' },
    })
    fireEvent.click(screen.getByText('Generate plan'))
    expect(await screen.findByText(/isn't configured yet/i)).toBeInTheDocument()
  })

  it('shows a Modify title and uses the modify endpoint for a program', async () => {
    const modify = vi.spyOn(api, 'coachModifyProgram').mockResolvedValue({
      program_id: 3,
      preview: PREVIEW,
      completed_preserved: 0,
      future_count: 4,
    })
    renderWithProviders(
      <CoachSheet open onClose={() => {}} onSaved={() => {}} program={{ id: 3, name: 'My Block' }} />,
    )
    expect(screen.getByText('Modify: My Block')).toBeInTheDocument()
    fireEvent.change(screen.getByPlaceholderText(/Shift everything/i), {
      target: { value: 'move to mondays' },
    })
    fireEvent.click(screen.getByText('Preview changes'))
    await waitFor(() => expect(modify).toHaveBeenCalledWith(3, 'move to mondays'))
    expect(await screen.findByText('Apply changes')).toBeInTheDocument()
  })

  it('shows the active objective + constraints banner in create mode', async () => {
    vi.spyOn(api, 'activeObjective').mockResolvedValue({
      objective: {
        id: 1,
        name: 'Climb Baker',
        kind: 'dated',
        target_date: '2026-09-05',
        sport: 'alpine',
        demands_profile: null,
        is_primary: true,
        created_at: '',
        updated_at: '',
      },
      constraints: [
        {
          id: 2,
          kind: 'injury',
          label: 'recovering L4-L5 disc',
          directives: null,
          defer_to_professional: true,
          is_active: true,
          created_at: '',
          updated_at: '',
        },
      ],
    })
    renderWithProviders(<CoachSheet open onClose={() => {}} onSaved={() => {}} />)
    expect(await screen.findByText(/Building toward: Climb Baker/)).toBeInTheDocument()
    expect(screen.getByText(/recovering L4-L5 disc/)).toBeInTheDocument()
    expect(screen.getByText(/defer to PT/)).toBeInTheDocument()
  })

  it('shows the routines the coach will create in the preview', async () => {
    vi.spyOn(api, 'coachGenerate').mockResolvedValue({
      ...PREVIEW,
      created_routines: [
        { key: 'lower', name: 'Lower + Carry', exercise_names: ['Step-up', 'Farmers Walk'] },
      ],
    })
    renderWithProviders(<CoachSheet open onClose={() => {}} onSaved={() => {}} />)
    fireEvent.change(screen.getByPlaceholderText(/Run both my routines/i), {
      target: { value: 'train me for Baker' },
    })
    fireEvent.click(screen.getByText('Generate plan'))
    expect(await screen.findByText('New routines the coach will create')).toBeInTheDocument()
    expect(screen.getByText('Lower + Carry')).toBeInTheDocument()
    expect(screen.getByText(/Step-up · Farmers Walk/)).toBeInTheDocument()
  })
})
