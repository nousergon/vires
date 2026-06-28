import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import { renderWithProviders, SETTINGS } from '../test/utils'
import PlanPage from './PlanPage'
import { api } from '../lib/api'
import { isoDate } from '../lib/calendar'

beforeEach(() => vi.restoreAllMocks())

function mockEmpty() {
  vi.spyOn(api, 'calendar').mockResolvedValue([])
  vi.spyOn(api, 'listPrograms').mockResolvedValue([])
  vi.spyOn(api, 'listTemplates').mockResolvedValue([])
}

describe('PlanPage', () => {
  it('renders the month grid with Sunday-first weekday headers', async () => {
    mockEmpty()
    renderWithProviders(<PlanPage />)
    expect(await screen.findByText('Plan')).toBeInTheDocument()
    // Sunday-first header row (grid renders after the calendar query resolves)
    const sun = await screen.findByText('Sun')
    expect(sun.parentElement?.textContent).toBe('SunMonTueWedThuFriSat')
    // the coach entry point is present
    expect(screen.getByText('✨ Coach')).toBeInTheDocument()
  })

  it('opens the coach sheet when ✨ Coach is tapped', async () => {
    mockEmpty()
    renderWithProviders(<PlanPage />)
    fireEvent.click(await screen.findByText('✨ Coach'))
    // CoachSheet (create mode) shows its prompt
    expect(await screen.findByText(/lays workouts onto your calendar/i)).toBeInTheDocument()
  })

  it('lists active programs from the API', async () => {
    vi.spyOn(api, 'calendar').mockResolvedValue([])
    vi.spyOn(api, 'listTemplates').mockResolvedValue([])
    vi.spyOn(api, 'listPrograms').mockResolvedValue([
      {
        id: 1,
        name: '8-Week Block',
        goal_text: null,
        start_date: '2026-06-29',
        end_date: '2026-08-20',
        status: 'active',
        planned_count: 16,
        completed_count: 2,
      },
    ])
    renderWithProviders(<PlanPage />)
    expect(await screen.findByText('8-Week Block')).toBeInTheDocument()
    expect(screen.getByText(/2\/16 done/)).toBeInTheDocument()
    expect(screen.getByText('Modify')).toBeInTheDocument()
  })

  it('reviews a planned routine without starting it', async () => {
    const iso = isoDate(new Date())
    vi.spyOn(api, 'calendar').mockResolvedValue([
      {
        kind: 'planned',
        date: iso,
        id: 5,
        name: 'Lower + Carry',
        status: 'planned',
        program_id: 1,
        template_id: 2,
        exercise_count: 1,
        session_id: null,
      },
    ])
    vi.spyOn(api, 'listPrograms').mockResolvedValue([])
    vi.spyOn(api, 'listTemplates').mockResolvedValue([])
    vi.spyOn(api, 'getSettings').mockResolvedValue(SETTINGS)
    const getP = vi.spyOn(api, 'getPlanned').mockResolvedValue({
      id: 5,
      program_id: 1,
      template_id: 2,
      scheduled_date: iso,
      name: 'Lower + Carry',
      notes: null,
      week_index: 1,
      status: 'planned',
      created_by: 'coach',
      session_id: null,
      exercises: [
        {
          id: 11,
          order_index: 0,
          exercise: { id: 101, name: 'Step-up', primary_muscles: [], equipment: null, is_timed: false },
          target_sets: 3,
          target_reps: 8,
          target_weight: 95,
          target_duration_seconds: null,
          rest_seconds: null,
          notes: null,
        },
      ],
    })
    const startSpy = vi.spyOn(api, 'startPlanned')

    renderWithProviders(<PlanPage />)
    fireEvent.click(await screen.findByLabelText(iso)) // open the day
    fireEvent.click(await screen.findByText('view routine')) // expand the prescription

    expect(await screen.findByText('Step-up')).toBeInTheDocument()
    expect(screen.getByText('3×8 @ 95lb')).toBeInTheDocument()
    expect(getP).toHaveBeenCalledWith(5)
    expect(startSpy).not.toHaveBeenCalled() // reviewed, NOT started
  })
})
