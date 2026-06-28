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
        name: 'Leg Day',
        started_at: '2026-06-28T18:00:00Z',
        ended_at: '2026-06-28T19:00:00Z',
        exercise_count: 2,
        set_count: 6,
        total_volume: 1200,
      },
    ])
    vi.spyOn(api, 'records').mockResolvedValue([])
    renderWithProviders(<HistoryPage />)
    expect(await screen.findByText('Leg Day')).toBeInTheDocument()
    expect(screen.getByText(/2 exercises/)).toBeInTheDocument()
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

  it('shows an empty state with no records', async () => {
    mockSettings()
    vi.spyOn(api, 'listWorkouts').mockResolvedValue([])
    vi.spyOn(api, 'records').mockResolvedValue([])
    renderWithProviders(<HistoryPage />)
    fireEvent.click(await screen.findByText('🏆 Records'))
    expect(await screen.findByText('No records yet')).toBeInTheDocument()
  })
})
