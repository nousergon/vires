import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import { renderWithProviders, SETTINGS, makeObjective, makeActiveObjective } from '../test/utils'
import PlanPage from './PlanPage'
import { api } from '../lib/api'
import { isoDate } from '../lib/calendar'

beforeEach(() => vi.restoreAllMocks())

function mockEmpty() {
  vi.spyOn(api, 'calendar').mockResolvedValue([])
  vi.spyOn(api, 'listPrograms').mockResolvedValue([])
  vi.spyOn(api, 'listTemplates').mockResolvedValue([])
  vi.spyOn(api, 'activeObjective').mockResolvedValue(makeActiveObjective())
  vi.spyOn(api, 'listObjectives').mockResolvedValue([])
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
        coach_summary: 'Ramp from 10 to 4 reps, deload week 4.',
        objective_id: null,
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
    // the coach's strategy shows on the program card
    expect(screen.getByText('Ramp from 10 to 4 reps, deload week 4.')).toBeInTheDocument()
  })

  it("shows the coach's strategy on the focus objective tile", async () => {
    vi.spyOn(api, 'calendar').mockResolvedValue([])
    vi.spyOn(api, 'listTemplates').mockResolvedValue([])
    vi.spyOn(api, 'listPrograms').mockResolvedValue([])
    vi.spyOn(api, 'listObjectives').mockResolvedValue([])
    vi.spyOn(api, 'activeObjective').mockResolvedValue(
      makeActiveObjective({
        objective: makeObjective({ id: 1, name: 'Climb Baker' }),
        active_program: {
          program_id: 7,
          name: 'Baker Block',
          coach_summary: 'Base, then peak strength, then taper to the summit.',
        },
      }),
    )
    renderWithProviders(<PlanPage />)
    expect(await screen.findByText("Coach's strategy")).toBeInTheDocument()
    expect(
      screen.getByText('Base, then peak strength, then taper to the summit.'),
    ).toBeInTheDocument()
  })

  it('lists multiple objectives with the focus marked and others as pins', async () => {
    vi.spyOn(api, 'calendar').mockResolvedValue([])
    vi.spyOn(api, 'listTemplates').mockResolvedValue([])
    vi.spyOn(api, 'listPrograms').mockResolvedValue([])
    const focus = makeObjective({ id: 1, name: 'Run a 50k', target_date: '2026-07-15' })
    const later = makeObjective({
      id: 2,
      name: 'Climb Baker',
      target_date: '2026-09-05',
      is_primary: false,
    })
    vi.spyOn(api, 'listObjectives').mockResolvedValue([focus, later])
    vi.spyOn(api, 'activeObjective').mockResolvedValue(
      makeActiveObjective({ objective: focus, objectives: [focus, later] }),
    )
    renderWithProviders(<PlanPage />)
    // both objectives are listed
    expect(await screen.findByText('Run a 50k')).toBeInTheDocument()
    expect(screen.getByText('Climb Baker')).toBeInTheDocument()
    // exactly one Focus badge (the derived focus)
    expect(screen.getAllByText('Focus')).toHaveLength(1)
  })

  it('renders a dated objective as an event on the calendar', async () => {
    const iso = isoDate(new Date())
    vi.spyOn(api, 'calendar').mockResolvedValue([
      {
        kind: 'objective',
        date: iso,
        id: 9,
        name: 'Climb Baker',
        status: 'peak',
        objective_id: 9,
        objective_name: 'Climb Baker',
        exercise_count: 0,
      },
    ])
    vi.spyOn(api, 'listPrograms').mockResolvedValue([])
    vi.spyOn(api, 'listTemplates').mockResolvedValue([])
    vi.spyOn(api, 'listObjectives').mockResolvedValue([])
    vi.spyOn(api, 'activeObjective').mockResolvedValue(makeActiveObjective())
    renderWithProviders(<PlanPage />)
    // the legend documents the new objective marker
    expect(await screen.findByText('objective')).toBeInTheDocument()
    // tapping the peak day surfaces the objective in the day sheet
    fireEvent.click(await screen.findByLabelText(iso))
    expect(await screen.findByText('Climb Baker')).toBeInTheDocument()
    expect(screen.getByText('🎯 peak / target day')).toBeInTheDocument()
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
