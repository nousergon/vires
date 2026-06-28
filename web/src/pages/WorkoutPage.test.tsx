import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import {
  renderWithProviders,
  SETTINGS,
  makeBrief,
  makeSession,
  makeSessionExercise,
  makeSet,
  makeTemplateSummary,
} from '../test/utils'
import WorkoutPage, { ACTIVE_KEY } from './WorkoutPage'
import { api } from '../lib/api'

beforeEach(() => {
  vi.restoreAllMocks()
  localStorage.removeItem(ACTIVE_KEY)
  vi.spyOn(api, 'getSettings').mockResolvedValue(SETTINGS)
})

describe('WorkoutPage — StartView (no active workout)', () => {
  it('lists routines and starts an empty workout', async () => {
    vi.spyOn(api, 'listTemplates').mockResolvedValue([makeTemplateSummary({ id: 7, name: 'Push Day' })])
    const start = vi.spyOn(api, 'startWorkout').mockResolvedValue(makeSession({ id: 42 }))
    vi.spyOn(api, 'getWorkout').mockResolvedValue(makeSession({ id: 42 }))

    renderWithProviders(<WorkoutPage />)
    expect(await screen.findByText('Train')).toBeInTheDocument()
    expect(await screen.findByText('Push Day')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Start empty workout'))
    await waitFor(() => expect(start).toHaveBeenCalledWith({ template_id: null }))
    // active id persisted → ActiveWorkout renders
    await waitFor(() => expect(localStorage.getItem(ACTIVE_KEY)).toBe('42'))
  })

  it('starts from a routine', async () => {
    vi.spyOn(api, 'listTemplates').mockResolvedValue([makeTemplateSummary({ id: 7, name: 'Push Day' })])
    const start = vi.spyOn(api, 'startWorkout').mockResolvedValue(makeSession({ id: 9 }))
    vi.spyOn(api, 'getWorkout').mockResolvedValue(makeSession({ id: 9 }))
    renderWithProviders(<WorkoutPage />)
    fireEvent.click(await screen.findByText('Start'))
    await waitFor(() => expect(start).toHaveBeenCalledWith({ template_id: 7 }))
  })

  it('shows an empty state with no routines', async () => {
    vi.spyOn(api, 'listTemplates').mockResolvedValue([])
    renderWithProviders(<WorkoutPage />)
    expect(await screen.findByText('No routines yet')).toBeInTheDocument()
  })
})

describe('WorkoutPage — ActiveWorkout', () => {
  beforeEach(() => localStorage.setItem(ACTIVE_KEY, '10'))

  it('renders the active session with its exercises and sets', async () => {
    vi.spyOn(api, 'getWorkout').mockResolvedValue(makeSession())
    renderWithProviders(<WorkoutPage />)
    expect(await screen.findByText('Push Day')).toBeInTheDocument()
    expect(screen.getByText('Bench Press')).toBeInTheDocument()
    expect(screen.getByText('Finish')).toBeInTheDocument()
    expect(screen.getByText('+ Add exercise')).toBeInTheDocument()
    expect(screen.getByDisplayValue('135')).toBeInTheDocument() // weight cell
  })

  it('adds a set (uses target/ghost values)', async () => {
    vi.spyOn(api, 'getWorkout').mockResolvedValue(makeSession())
    const log = vi.spyOn(api, 'logSet').mockResolvedValue(makeSet({ id: 1001 }))
    renderWithProviders(<WorkoutPage />)
    fireEvent.click(await screen.findByText('+ Add set'))
    await waitFor(() => expect(log).toHaveBeenCalledWith(10, 100, { reps: 8, weight: 135 }))
  })

  it('marks a set done and starts the rest timer', async () => {
    vi.spyOn(api, 'getWorkout').mockResolvedValue(makeSession())
    const upd = vi.spyOn(api, 'updateSet').mockResolvedValue(makeSet({ completed_at: '2026-06-28T18:05:00Z' }))
    renderWithProviders(<WorkoutPage />)
    await screen.findByText('Bench Press')
    fireEvent.click(screen.getByTitle('Mark set done'))
    await waitFor(() => expect(upd).toHaveBeenCalled())
    expect(upd.mock.calls[0][3]).toMatchObject({ done: true })
    // rest timer bar appears
    expect(await screen.findByText('Rest')).toBeInTheDocument()
    expect(screen.getByText('Skip')).toBeInTheDocument()
  })

  it('edits weight on blur', async () => {
    vi.spyOn(api, 'getWorkout').mockResolvedValue(makeSession())
    const upd = vi.spyOn(api, 'updateSet').mockResolvedValue(makeSet())
    renderWithProviders(<WorkoutPage />)
    const weight = await screen.findByDisplayValue('135')
    fireEvent.change(weight, { target: { value: '145' } })
    fireEvent.blur(weight)
    await waitFor(() => expect(upd).toHaveBeenCalledWith(10, 100, 1000, { weight: 145 }))
  })

  it('toggles warm-up and deletes a set', async () => {
    vi.spyOn(api, 'getWorkout').mockResolvedValue(makeSession())
    const upd = vi.spyOn(api, 'updateSet').mockResolvedValue(makeSet())
    const del = vi.spyOn(api, 'deleteSet').mockResolvedValue(undefined as unknown as void)
    renderWithProviders(<WorkoutPage />)
    fireEvent.click(await screen.findByTitle('Toggle warm-up'))
    await waitFor(() => expect(upd).toHaveBeenCalledWith(10, 100, 1000, { is_warmup: true }))
    fireEvent.click(screen.getByText('✕'))
    await waitFor(() => expect(del).toHaveBeenCalledWith(10, 100, 1000))
  })

  it('removes an exercise', async () => {
    vi.spyOn(api, 'getWorkout').mockResolvedValue(makeSession())
    const rm = vi.spyOn(api, 'removeWorkoutExercise').mockResolvedValue(undefined as unknown as void)
    renderWithProviders(<WorkoutPage />)
    fireEvent.click(await screen.findByText('remove'))
    await waitFor(() => expect(rm).toHaveBeenCalledWith(10, 100))
  })

  it('finishes the workout', async () => {
    vi.spyOn(api, 'getWorkout').mockResolvedValue(makeSession())
    const fin = vi.spyOn(api, 'finishWorkout').mockResolvedValue(makeSession({ ended_at: 'x' }))
    renderWithProviders(<WorkoutPage />)
    fireEvent.click(await screen.findByText('Finish'))
    await waitFor(() => expect(fin).toHaveBeenCalledWith(10))
    await waitFor(() => expect(localStorage.getItem(ACTIVE_KEY)).toBeNull())
  })

  it('discards the workout after confirm', async () => {
    vi.spyOn(api, 'getWorkout').mockResolvedValue(makeSession())
    const del = vi.spyOn(api, 'deleteWorkout').mockResolvedValue(undefined as unknown as void)
    vi.stubGlobal('confirm', () => true)
    renderWithProviders(<WorkoutPage />)
    fireEvent.click(await screen.findByText('Discard workout'))
    await waitFor(() => expect(del).toHaveBeenCalledWith(10))
  })

  it('opens the exercise picker', async () => {
    vi.spyOn(api, 'getWorkout').mockResolvedValue(makeSession())
    renderWithProviders(<WorkoutPage />)
    fireEvent.click(await screen.findByText('+ Add exercise'))
    expect(await screen.findByText('Add exercise')).toBeInTheDocument() // picker sheet title
  })

  it('renders a previous-performance hint', async () => {
    const se = makeSessionExercise({
      previous_performance: {
        session_id: 5,
        session_name: 'Prev',
        date: '2026-06-21',
        sets: [{ set_number: 1, reps: 8, weight: 130, rpe: null, is_warmup: false }],
      },
    })
    vi.spyOn(api, 'getWorkout').mockResolvedValue(makeSession({ exercises: [se] }))
    renderWithProviders(<WorkoutPage />)
    expect(await screen.findByText(/Last time/)).toHaveTextContent('130lb×8')
  })

  it('handles a timed (hold) exercise: start hold + mark done', async () => {
    const timed = makeSessionExercise({
      id: 200,
      exercise: makeBrief({ id: 2, name: 'Plank', is_timed: true, equipment: 'bodyweight' }),
      target_duration_seconds: 45,
      sets: [makeSet({ id: 2000, reps: null, weight: null, duration_seconds: 45 })],
    })
    vi.spyOn(api, 'getWorkout').mockResolvedValue(makeSession({ exercises: [timed] }))
    const upd = vi.spyOn(api, 'updateSet').mockResolvedValue(makeSet())
    renderWithProviders(<WorkoutPage />)
    await screen.findByText('Plank')
    fireEvent.click(screen.getByTitle('Start hold')) // ▶ → hold timer
    expect(await screen.findByText('Hold')).toBeInTheDocument()
    fireEvent.click(screen.getByTitle('Mark done')) // ✓
    await waitFor(() => expect(upd).toHaveBeenCalled())
    expect(upd.mock.calls[0][3]).toMatchObject({ done: true, duration_seconds: 45 })
  })
})
