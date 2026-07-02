import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import { renderWithProviders, SETTINGS } from '../test/utils'
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
        ruck: null,
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
        ruck: null,
        activity: { template_key: 'climbing_indoor_toprope', duration_s: 5400, regions: 'upper', intensity: 'moderate' },
      },
    ])
    vi.spyOn(api, 'records').mockResolvedValue([])
    renderWithProviders(<HistoryPage />)
    expect(await screen.findByText('🏃 Indoor top-rope')).toBeInTheDocument()
    expect(screen.getByText(/upper/)).toBeInTheDocument()
    expect(screen.getByText(/moderate/)).toBeInTheDocument()
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
      { id: 1, session_type: 'strength', name: 'Test A', started_at: '2026-06-28T18:00:00Z', ended_at: '2026-06-28T19:00:00Z', exercise_count: 1, set_count: 3, total_volume: 100, ruck: null, activity: null },
      { id: 2, session_type: 'strength', name: 'Test B', started_at: '2026-06-27T18:00:00Z', ended_at: '2026-06-27T19:00:00Z', exercise_count: 1, set_count: 3, total_volume: 100, ruck: null, activity: null },
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
      { id: 9, session_type: 'strength', name: 'Test C', started_at: '2026-06-28T18:00:00Z', ended_at: '2026-06-28T19:00:00Z', exercise_count: 0, set_count: 0, total_volume: 0, ruck: null, activity: null },
    ])
    vi.spyOn(api, 'records').mockResolvedValue([])
    vi.spyOn(api, 'getWorkout').mockResolvedValue({
      id: 9, session_type: 'strength', name: 'Test C', started_at: '2026-06-28T18:00:00Z', ended_at: '2026-06-28T19:00:00Z',
      notes: null, template_id: null, exercises: [], ruck: null, activity: null,
    })
    const del = vi.spyOn(api, 'deleteWorkout').mockResolvedValue(undefined)
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    renderWithProviders(<HistoryPage />)
    fireEvent.click(await screen.findByText('Test C'))
    fireEvent.click(await screen.findByText('Delete workout'))
    await new Promise((r) => setTimeout(r, 0))
    expect(del).toHaveBeenCalledWith(9)
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
