import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import {
  makeActivityDetail,
  makeSession,
  makeSessionExercise,
  makeSet,
  renderWithProviders,
  SETTINGS,
} from '../test/utils'
import HistoryPage from './HistoryPage'
import { api } from '../lib/api'

beforeEach(() => vi.restoreAllMocks())

function mockSettings() {
  vi.spyOn(api, 'getSettings').mockResolvedValue(SETTINGS)
}

describe('HistoryPage', () => {
  it('lists finished workouts in the Sessions tab', async () => {
    mockSettings()
    vi.spyOn(api, 'listWorkouts').mockResolvedValue([
      {
        id: 1,
        session_type: 'strength',
        name: 'Leg Day',
        started_at: '2026-06-28T18:00:00Z',
        ended_at: '2026-06-28T19:00:00Z',
        exercise_count: 2,
        set_count: 6,
        total_volume: 1200,
        tags: [],
        energy_level: null,
        workout_intensity: null,
        challenge_level: null,
        activity: null,
      },
    ])
    vi.spyOn(api, 'records').mockResolvedValue([])
    renderWithProviders(<HistoryPage />)
    expect(await screen.findByText('Leg Day')).toBeInTheDocument()
    expect(screen.getByText(/2 exercises/)).toBeInTheDocument()
  })

  it('shows a generic activity session with its regions/intensity summary', async () => {
    mockSettings()
    vi.spyOn(api, 'listWorkouts').mockResolvedValue([
      {
        id: 2,
        session_type: 'activity',
        name: 'Indoor top-rope',
        started_at: '2026-06-28T18:00:00Z',
        ended_at: '2026-06-28T19:30:00Z',
        exercise_count: 0,
        set_count: 0,
        total_volume: 0,
        tags: [],
        energy_level: null,
        workout_intensity: null,
        challenge_level: null,
        activity: makeActivityDetail({
          template_key: 'climbing_indoor_toprope',
          duration_s: 5400,
          regions: 'upper',
          intensity: 'moderate',
        }),
      },
    ])
    vi.spyOn(api, 'records').mockResolvedValue([])
    renderWithProviders(<HistoryPage />)
    expect(await screen.findByText('🏃 Indoor top-rope')).toBeInTheDocument()
    expect(screen.getByText(/upper/)).toBeInTheDocument()
    expect(screen.getByText(/moderate/)).toBeInTheDocument()
  })

  it('shows a loaded hike with the 🎒 badge and pack/distance/load summary', async () => {
    mockSettings()
    const loadedHike = makeActivityDetail({
      template_key: 'hike',
      pack_weight_kg: 20.4,
      bodyweight_kg: 81.6,
      distance_m: 8000,
      elevation_gain_m: 300,
      metabolic_cost_kj: 2500,
    })
    vi.spyOn(api, 'listWorkouts').mockResolvedValue([
      {
        id: 3,
        session_type: 'activity',
        name: 'Morning hike',
        started_at: '2026-06-28T13:00:00Z',
        ended_at: '2026-06-28T15:00:00Z',
        exercise_count: 0,
        set_count: 0,
        total_volume: 0,
        tags: [],
        energy_level: null,
        workout_intensity: null,
        challenge_level: null,
        activity: loadedHike,
      },
    ])
    vi.spyOn(api, 'records').mockResolvedValue([])
    vi.spyOn(api, 'getWorkout').mockResolvedValue({
      id: 3,
      session_type: 'activity',
      name: 'Morning hike',
      started_at: '2026-06-28T13:00:00Z',
      ended_at: '2026-06-28T15:00:00Z',
      notes: null,
      tags: [],
      energy_level: null,
      workout_intensity: null,
      challenge_level: null,
      template_id: null,
      exercises: [],
      activity: loadedHike,
      recurrence_source_id: null,
    })
    renderWithProviders(<HistoryPage />)
    expect(await screen.findByText('🎒 Morning hike')).toBeInTheDocument()
    expect(screen.getByText(/lb/)).toBeInTheDocument()

    fireEvent.click(screen.getByText('🎒 Morning hike'))
    expect(await screen.findByText('Pack')).toBeInTheDocument()
    expect(screen.getByText('Load')).toBeInTheDocument()
    expect(screen.getByText('Distance')).toBeInTheDocument()
  })

  it('shows tags (including pre-workout fuel logged as a tag) and energy/intensity in the detail sheet', async () => {
    mockSettings()
    vi.spyOn(api, 'listWorkouts').mockResolvedValue([
      { id: 7, session_type: 'strength', name: 'Push Day', started_at: '2026-06-28T18:00:00Z', ended_at: '2026-06-28T19:00:00Z', exercise_count: 0, set_count: 0, total_volume: 0, tags: ['push'], energy_level: 7, workout_intensity: 9, challenge_level: null, activity: null },
    ])
    vi.spyOn(api, 'records').mockResolvedValue([])
    vi.spyOn(api, 'getWorkout').mockResolvedValue(
      makeSession({
        id: 7,
        name: 'Push Day',
        exercises: [],
        tags: ['push', 'fasted', 'black coffee', 'creatine'],
        energy_level: 7,
        workout_intensity: 9,
      }),
    )
    renderWithProviders(<HistoryPage />)
    fireEvent.click(await screen.findByText('Push Day'))
    expect(await screen.findByText('fasted')).toBeInTheDocument()
    expect(screen.getByText('black coffee')).toBeInTheDocument()
    expect(screen.getByText('creatine')).toBeInTheDocument()
    expect(screen.getByText('7 / 10')).toBeInTheDocument()
    expect(screen.getByText('9 / 10')).toBeInTheDocument()
  })

  it('switches to Records and shows per-exercise bests', async () => {
    mockSettings()
    vi.spyOn(api, 'listWorkouts').mockResolvedValue([])
    vi.spyOn(api, 'records').mockResolvedValue([
      {
        exercise: { id: 5, name: 'Bench Press', primary_muscles: [], equipment: null, is_timed: false },
        is_timed: false,
        est_1rm: { value: 247.5, weight: 225, reps: 3, date: '2026-06-20' },
        heaviest: { value: 225, weight: 225, reps: 1, date: '2026-06-20' },
        best_set_volume: { value: 1350, weight: 135, reps: 10, date: '2026-06-10' },
        most_reps: { value: 12, weight: 95, reps: 12, date: '2026-06-05' },
        longest_hold: null,
      },
    ])
    renderWithProviders(<HistoryPage />)
    fireEvent.click(await screen.findByText('🏆 Records'))
    expect(await screen.findByText('Bench Press')).toBeInTheDocument()
    expect(screen.getByText('Est. 1RM')).toBeInTheDocument()
    expect(screen.getByText('247.5 lb')).toBeInTheDocument()
    // window selector present
    expect(screen.getByText('Quarter')).toBeInTheDocument()
  })

  it('selects workouts and bulk-deletes them', async () => {
    mockSettings()
    vi.spyOn(api, 'listWorkouts').mockResolvedValue([
      { id: 1, session_type: 'strength', name: 'Test A', started_at: '2026-06-28T18:00:00Z', ended_at: '2026-06-28T19:00:00Z', exercise_count: 1, set_count: 3, total_volume: 100, tags: [], energy_level: null, workout_intensity: null, challenge_level: null, activity: null },
      { id: 2, session_type: 'strength', name: 'Test B', started_at: '2026-06-27T18:00:00Z', ended_at: '2026-06-27T19:00:00Z', exercise_count: 1, set_count: 3, total_volume: 100, tags: [], energy_level: null, workout_intensity: null, challenge_level: null, activity: null },
    ])
    vi.spyOn(api, 'records').mockResolvedValue([])
    const del = vi.spyOn(api, 'deleteWorkout').mockResolvedValue(undefined)
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    renderWithProviders(<HistoryPage />)
    fireEvent.click(await screen.findByText('Select'))
    fireEvent.click(screen.getByText('Test A')) // select first
    fireEvent.click(screen.getByText('Delete 1'))
    await new Promise((r) => setTimeout(r, 0))
    expect(del).toHaveBeenCalledWith(1)
    expect(del).toHaveBeenCalledTimes(1)
  })

  it('deletes a single workout from the detail sheet', async () => {
    mockSettings()
    vi.spyOn(api, 'listWorkouts').mockResolvedValue([
      { id: 9, session_type: 'strength', name: 'Test C', started_at: '2026-06-28T18:00:00Z', ended_at: '2026-06-28T19:00:00Z', exercise_count: 0, set_count: 0, total_volume: 0, tags: [], energy_level: null, workout_intensity: null, challenge_level: null, activity: null },
    ])
    vi.spyOn(api, 'records').mockResolvedValue([])
    vi.spyOn(api, 'getWorkout').mockResolvedValue({
      id: 9, session_type: 'strength', name: 'Test C', started_at: '2026-06-28T18:00:00Z', ended_at: '2026-06-28T19:00:00Z',
      notes: null, tags: [], energy_level: null, workout_intensity: null, challenge_level: null,
      template_id: null, exercises: [], activity: null, recurrence_source_id: null,
    })
    const del = vi.spyOn(api, 'deleteWorkout').mockResolvedValue(undefined)
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    renderWithProviders(<HistoryPage />)
    fireEvent.click(await screen.findByText('Test C'))
    fireEvent.click(await screen.findByText('Delete workout'))
    await new Promise((r) => setTimeout(r, 0))
    expect(del).toHaveBeenCalledWith(9)
  })

  it('edits a logged set weight/reps from the History detail sheet', async () => {
    mockSettings()
    vi.spyOn(api, 'listWorkouts').mockResolvedValue([
      { id: 9, session_type: 'strength', name: 'Test D', started_at: '2026-06-28T18:00:00Z', ended_at: '2026-06-28T19:00:00Z', exercise_count: 1, set_count: 1, total_volume: 135, tags: [], energy_level: null, workout_intensity: null, challenge_level: null, activity: null },
    ])
    vi.spyOn(api, 'records').mockResolvedValue([])
    const session = makeSession({
      id: 9,
      name: 'Test D',
      exercises: [makeSessionExercise({ sets: [makeSet({ id: 500, set_number: 1, weight: 135, reps: 8 })] })],
    })
    vi.spyOn(api, 'getWorkout').mockResolvedValue(session)
    const update = vi.spyOn(api, 'updateSet').mockResolvedValue(makeSet({ id: 500, weight: 140, reps: 8 }))

    renderWithProviders(<HistoryPage />)
    fireEvent.click(await screen.findByText('Test D'))
    fireEvent.click(await screen.findByText('Edit sets'))

    const weightInput = await screen.findByLabelText(/set 1 weight/)
    fireEvent.change(weightInput, { target: { value: '140' } })
    fireEvent.blur(weightInput)

    await waitFor(() => expect(update).toHaveBeenCalledWith(9, 100, 500, { weight: 140 }))
  })

  it('shows an empty state with no records', async () => {
    mockSettings()
    vi.spyOn(api, 'listWorkouts').mockResolvedValue([])
    vi.spyOn(api, 'records').mockResolvedValue([])
    renderWithProviders(<HistoryPage />)
    fireEvent.click(await screen.findByText('🏆 Records'))
    expect(await screen.findByText('No records yet')).toBeInTheDocument()
  })
})
