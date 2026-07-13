import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderWithProviders, makeHit } from '../test/utils'
import ExerciseTrend from './ExerciseTrend'
import { api } from '../lib/api'
import type { ExercisePerformance } from '../lib/api'

beforeEach(() => vi.restoreAllMocks())

function pickExercise(name = 'Bench Press') {
  fireEvent.click(screen.getByText('Choose an exercise'))
  fireEvent.change(screen.getByPlaceholderText(/Search/), { target: { value: name } })
  return screen.findByText(name).then((el) => fireEvent.click(el))
}

describe('ExerciseTrend', () => {
  it('shows a chart of max weight per session after picking an exercise', async () => {
    vi.spyOn(api, 'searchExercises').mockResolvedValue([makeHit({ id: 3, name: 'Bench Press' })])
    const history: ExercisePerformance[] = [
      {
        session_id: 2,
        session_name: 'Push B',
        date: '2026-07-02T18:00:00Z',
        sets: [
          { set_number: 1, reps: 5, weight: 185, rpe: null, duration_seconds: null, is_warmup: false },
        ],
      },
      {
        session_id: 1,
        session_name: 'Push A',
        date: '2026-06-25T18:00:00Z',
        sets: [
          { set_number: 1, reps: 5, weight: 135, rpe: null, duration_seconds: null, is_warmup: true },
          { set_number: 2, reps: 5, weight: 175, rpe: null, duration_seconds: null, is_warmup: false },
        ],
      },
    ]
    const fetchHistory = vi.spyOn(api, 'exerciseHistory').mockResolvedValue(history)

    renderWithProviders(<ExerciseTrend />)
    await pickExercise('Bench Press')

    await waitFor(() => expect(fetchHistory).toHaveBeenCalledWith(3, 10))
    expect(await screen.findByText('Max weight per session (lb)')).toBeInTheDocument()
    expect(screen.getByText('2 sessions')).toBeInTheDocument()
    // Oldest -> newest, warmups excluded from the max.
    const svg = document.querySelector('svg') as SVGElement
    expect(svg.textContent).toContain('175')
    expect(svg.textContent).toContain('185')
    expect(svg.textContent).not.toContain('135')
  })

  it('re-fetches with the new limit when a different window is selected', async () => {
    vi.spyOn(api, 'searchExercises').mockResolvedValue([makeHit({ id: 3, name: 'Bench Press' })])
    const fetchHistory = vi.spyOn(api, 'exerciseHistory').mockResolvedValue([])

    renderWithProviders(<ExerciseTrend />)
    await pickExercise('Bench Press')
    await waitFor(() => expect(fetchHistory).toHaveBeenCalledWith(3, 10))

    fireEvent.click(screen.getByText('Last 20'))
    await waitFor(() => expect(fetchHistory).toHaveBeenCalledWith(3, 20))
  })

  it('shows an empty state when the exercise has no working sets logged', async () => {
    vi.spyOn(api, 'searchExercises').mockResolvedValue([makeHit({ id: 3, name: 'Bench Press' })])
    vi.spyOn(api, 'exerciseHistory').mockResolvedValue([])

    renderWithProviders(<ExerciseTrend />)
    await pickExercise('Bench Press')

    expect(await screen.findByText('No logged sets yet')).toBeInTheDocument()
  })

  it('charts longest hold (not weight) for a timed exercise', async () => {
    vi.spyOn(api, 'searchExercises').mockResolvedValue([
      makeHit({ id: 5, name: 'Plank', is_timed: true }),
    ])
    vi.spyOn(api, 'exerciseHistory').mockResolvedValue([
      {
        session_id: 1,
        session_name: 'Core',
        date: '2026-07-01T18:00:00Z',
        sets: [
          { set_number: 1, reps: null, weight: null, rpe: null, duration_seconds: 65, is_warmup: false },
        ],
      },
    ])

    renderWithProviders(<ExerciseTrend />)
    await pickExercise('Plank')

    expect(await screen.findByText('Longest hold per session')).toBeInTheDocument()
    const svg = document.querySelector('svg') as SVGElement
    expect(svg.textContent).toContain('1:05')
  })
})
