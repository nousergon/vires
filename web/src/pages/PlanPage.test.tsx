import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderWithProviders, SETTINGS, makeObjective, makeActiveObjective, makeSession } from '../test/utils'
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
  vi.spyOn(api, 'rescheduleMissed').mockResolvedValue([])
  vi.spyOn(api, 'listAilments').mockResolvedValue([])
  vi.spyOn(api, 'pendingAilmentCheckIns').mockResolvedValue([])
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

  it('shows coach summary on the Coach tab', async () => {
    vi.spyOn(api, 'calendar').mockResolvedValue([])
    vi.spyOn(api, 'listTemplates').mockResolvedValue([])
    vi.spyOn(api, 'rescheduleMissed').mockResolvedValue([])
    vi.spyOn(api, 'listObjectives').mockResolvedValue([])
    vi.spyOn(api, 'listAilments').mockResolvedValue([])
    vi.spyOn(api, 'pendingAilmentCheckIns').mockResolvedValue([])
    vi.spyOn(api, 'activeObjective').mockResolvedValue(makeActiveObjective())
    vi.spyOn(api, 'listPrograms').mockResolvedValue([
      {
        id: 1,
        name: 'Baker Taper',
        goal_text: null,
        coach_summary: 'Arrive fresh on summit day.',
        objective_id: null,
        start_date: '2026-06-29',
        end_date: '2026-07-02',
        status: 'active',
        planned_count: 2,
        completed_count: 2,
      },
    ])
    renderWithProviders(<PlanPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'Coach' }))
    expect(await screen.findByText('Arrive fresh on summit day.')).toBeInTheDocument()
  })

  it('lists active programs from the API', async () => {
    vi.spyOn(api, 'calendar').mockResolvedValue([])
    vi.spyOn(api, 'listTemplates').mockResolvedValue([])
    vi.spyOn(api, 'rescheduleMissed').mockResolvedValue([])
    vi.spyOn(api, 'listAilments').mockResolvedValue([])
    vi.spyOn(api, 'pendingAilmentCheckIns').mockResolvedValue([])
    vi.spyOn(api, 'activeObjective').mockResolvedValue(makeActiveObjective())
    vi.spyOn(api, 'listObjectives').mockResolvedValue([])
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
    // summary lives on the Coach tab, not the compact calendar program card
    expect(screen.queryByText('Ramp from 10 to 4 reps, deload week 4.')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Coach' }))
    expect(await screen.findByText('Ramp from 10 to 4 reps, deload week 4.')).toBeInTheDocument()
  })

  it("shows the coach's strategy on the focus objective tile", async () => {
    vi.spyOn(api, 'calendar').mockResolvedValue([])
    vi.spyOn(api, 'listTemplates').mockResolvedValue([])
    vi.spyOn(api, 'rescheduleMissed').mockResolvedValue([])
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
    vi.spyOn(api, 'rescheduleMissed').mockResolvedValue([])
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
    vi.spyOn(api, 'rescheduleMissed').mockResolvedValue([])
    renderWithProviders(<PlanPage />)
    // the legend documents the new objective marker
    expect(await screen.findByText('objective')).toBeInTheDocument()
    // tapping the peak day surfaces the objective in the day sheet
    fireEvent.click(await screen.findByLabelText(iso))
    expect(await screen.findByText('Climb Baker')).toBeInTheDocument()
    expect(screen.getByText('🎯 peak / target day')).toBeInTheDocument()
  })

  it('deletes an objective from the day sheet after confirming', async () => {
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
    vi.spyOn(api, 'rescheduleMissed').mockResolvedValue([])
    const del = vi.spyOn(api, 'deleteObjective').mockResolvedValue(undefined)
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    renderWithProviders(<PlanPage />)
    fireEvent.click(await screen.findByLabelText(iso))
    fireEvent.click(await screen.findByLabelText('Delete Climb Baker'))

    await waitFor(() => expect(del).toHaveBeenCalledWith(9))
  })

  it('opens the objective for editing when its day-sheet chip is tapped', async () => {
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
    // Focus left unset (default makeActiveObjective()) so the Agenda section
    // below the calendar doesn't ALSO render a "Climb Baker" tile — this test
    // is only about the day sheet's own chip, and a focus tile would make the
    // text query ambiguous.
    vi.spyOn(api, 'listObjectives').mockResolvedValue([
      makeObjective({ id: 9, name: 'Climb Baker', is_primary: true }),
    ])
    vi.spyOn(api, 'activeObjective').mockResolvedValue(makeActiveObjective())
    vi.spyOn(api, 'rescheduleMissed').mockResolvedValue([])

    renderWithProviders(<PlanPage />)
    fireEvent.click(await screen.findByLabelText(iso))
    fireEvent.click(await screen.findByText('Climb Baker'))

    expect(await screen.findByText('🎯 Edit objective')).toBeInTheDocument()
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
    vi.spyOn(api, 'rescheduleMissed').mockResolvedValue([])
    const getP = vi.spyOn(api, 'getPlanned').mockResolvedValue({
      id: 5,
      program_id: 1,
      template_id: 2,
      scheduled_date: iso,
      rescheduled_from: null,
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

  it('renders an upcoming activity as a marker distinct from objectives', async () => {
    mockEmpty()
    const iso = isoDate(new Date(Date.now() + 7 * 864e5)) // a week out — safely "upcoming"
    vi.spyOn(api, 'calendar').mockResolvedValue([
      {
        kind: 'session',
        date: iso,
        id: 3,
        name: 'Tuesday league game',
        status: 'upcoming',
        exercise_count: 0,
        session_type: 'activity',
        virtual: true,
      },
    ])
    renderWithProviders(<PlanPage />)
    // the legend documents the distinct upcoming-activity marker
    expect(await screen.findByText(/upcoming\s*activity/)).toBeInTheDocument()
    // it also surfaces in the merged Agenda list
    expect(await screen.findByText('Tuesday league game')).toBeInTheDocument()
    // tapping the day surfaces the activity as a marker chip (not a fuchsia band)
    fireEvent.click(await screen.findByLabelText(iso))
    expect(await screen.findAllByText('Tuesday league game')).not.toHaveLength(0)
    expect(screen.getByText('upcoming')).toBeInTheDocument()
  })

  it('opens the add-activity sheet from the Agenda section header', async () => {
    mockEmpty()
    renderWithProviders(<PlanPage />)
    fireEvent.click(await screen.findByText('+ Activity'))
    expect(await screen.findByText('Add activity')).toBeInTheDocument()
  })

  it('opens the add-objective sheet from the Agenda empty state', async () => {
    mockEmpty()
    renderWithProviders(<PlanPage />)
    fireEvent.click(await screen.findByText(/Set a goal/))
    expect(await screen.findByText('Add objective')).toBeInTheDocument()
  })

  it('shows the reschedule banner and invalidates the calendar when a workout moves', async () => {
    mockEmpty()
    vi.spyOn(api, 'rescheduleMissed').mockResolvedValue([
      {
        id: 5,
        program_id: null,
        template_id: null,
        scheduled_date: isoDate(new Date()),
        rescheduled_from: '2026-07-02',
        name: 'Upper Body',
        notes: null,
        week_index: null,
        status: 'planned',
        created_by: 'coach',
        session_id: null,
        exercises: [],
      },
    ])
    renderWithProviders(<PlanPage />)
    expect(await screen.findByText('🧠 The coach moved a missed workout')).toBeInTheDocument()
    expect(screen.getByText(/Upper Body/)).toBeInTheDocument()
  })

  it('dismissing the reschedule banner removes it', async () => {
    mockEmpty()
    vi.spyOn(api, 'rescheduleMissed').mockResolvedValue([
      {
        id: 5,
        program_id: null,
        template_id: null,
        scheduled_date: isoDate(new Date()),
        rescheduled_from: '2026-07-02',
        name: 'Upper Body',
        notes: null,
        week_index: null,
        status: 'planned',
        created_by: 'coach',
        session_id: null,
        exercises: [],
      },
    ])
    renderWithProviders(<PlanPage />)
    expect(await screen.findByText('🧠 The coach moved a missed workout')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Dismiss'))
    expect(screen.queryByText('🧠 The coach moved a missed workout')).not.toBeInTheDocument()
  })

  it('shows no banner when the reschedule check is a no-op', async () => {
    mockEmpty()
    renderWithProviders(<PlanPage />)
    expect(await screen.findByText('Plan')).toBeInTheDocument()
    expect(screen.queryByText(/The coach moved/)).not.toBeInTheDocument()
  })

  it('renders ONE card for a completed planned routine and opens view/tag', async () => {
    // The calendar API absorbs a fulfilled session into its planned entry —
    // the day sheet must show a single card (the July-3 duplicate bug), and
    // tapping "Completed" opens the logged session for tagging.
    const iso = isoDate(new Date())
    vi.spyOn(api, 'calendar').mockResolvedValue([
      {
        kind: 'planned',
        date: iso,
        id: 5,
        name: 'Lower + Carry',
        status: 'completed',
        program_id: 1,
        template_id: 2,
        exercise_count: 1,
        session_id: 77,
      },
    ])
    vi.spyOn(api, 'listPrograms').mockResolvedValue([])
    vi.spyOn(api, 'listTemplates').mockResolvedValue([])
    vi.spyOn(api, 'getSettings').mockResolvedValue(SETTINGS)
    vi.spyOn(api, 'rescheduleMissed').mockResolvedValue([])
    const getW = vi.spyOn(api, 'getWorkout').mockResolvedValue(
      makeSession({ id: 77, name: 'Lower + Carry', ended_at: '2026-07-03T19:00:00Z' }),
    )

    renderWithProviders(<PlanPage />)
    fireEvent.click(await screen.findByLabelText(iso)) // open the day
    // exactly one card for the routine
    expect(await screen.findAllByText('Lower + Carry')).toHaveLength(1)
    fireEvent.click(screen.getByText(/Completed ✓/))
    // the shared session-detail sheet opens with the tagging editor
    expect(await screen.findByText('Pre-workout food / drink / supps')).toBeInTheDocument()
    expect(screen.getByText('Energy level')).toBeInTheDocument()
    expect(screen.getByText('Workout intensity')).toBeInTheDocument()
    expect(getW).toHaveBeenCalledWith(77)
  })

  it('persists an after-the-fact intensity rating from the day sheet', async () => {
    const iso = isoDate(new Date())
    vi.spyOn(api, 'calendar').mockResolvedValue([
      {
        kind: 'planned',
        date: iso,
        id: 5,
        name: 'Lower + Carry',
        status: 'completed',
        program_id: 1,
        template_id: 2,
        exercise_count: 1,
        session_id: 77,
      },
    ])
    vi.spyOn(api, 'listPrograms').mockResolvedValue([])
    vi.spyOn(api, 'listTemplates').mockResolvedValue([])
    vi.spyOn(api, 'getSettings').mockResolvedValue(SETTINGS)
    vi.spyOn(api, 'rescheduleMissed').mockResolvedValue([])
    const session = makeSession({ id: 77, name: 'Lower + Carry', ended_at: '2026-07-03T19:00:00Z' })
    vi.spyOn(api, 'getWorkout').mockResolvedValue(session)
    const patch = vi.spyOn(api, 'updateWorkout').mockResolvedValue(session)

    renderWithProviders(<PlanPage />)
    fireEvent.click(await screen.findByLabelText(iso))
    fireEvent.click(await screen.findByText(/Completed ✓/))
    fireEvent.click(await screen.findByLabelText('Workout intensity 8'))
    expect(patch).toHaveBeenCalledWith(77, { workout_intensity: 8 })
  })

  it('makes an ad-hoc logged session tappable to view/tag', async () => {
    const iso = isoDate(new Date())
    vi.spyOn(api, 'calendar').mockResolvedValue([
      {
        kind: 'session',
        date: iso,
        id: 42,
        name: 'Garage Session',
        status: 'completed',
        session_type: 'strength',
        exercise_count: 3,
      },
    ])
    vi.spyOn(api, 'listPrograms').mockResolvedValue([])
    vi.spyOn(api, 'listTemplates').mockResolvedValue([])
    vi.spyOn(api, 'getSettings').mockResolvedValue(SETTINGS)
    vi.spyOn(api, 'rescheduleMissed').mockResolvedValue([])
    const getW = vi.spyOn(api, 'getWorkout').mockResolvedValue(
      makeSession({ id: 42, name: 'Garage Session', ended_at: '2026-07-03T19:00:00Z' }),
    )

    renderWithProviders(<PlanPage />)
    fireEvent.click(await screen.findByLabelText(iso))
    fireEvent.click(await screen.findByText(/view \/ tag/))
    expect(await screen.findByText('Pre-workout food / drink / supps')).toBeInTheDocument()
    expect(getW).toHaveBeenCalledWith(42)
  })
})
