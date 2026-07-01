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

  it('self-heals to the start view when the active session was deleted (404)', async () => {
    // localStorage points at session 10, but it was deleted → getWorkout 404s.
    vi.spyOn(api, 'getWorkout').mockRejectedValue(new Error('404: Workout not found'))
    vi.spyOn(api, 'listTemplates').mockResolvedValue([])
    renderWithProviders(<WorkoutPage />)
    // falls back to StartView instead of spinning forever, and clears the pointer
    expect(await screen.findByText('Start empty workout')).toBeInTheDocument()
    await waitFor(() => expect(localStorage.getItem(ACTIVE_KEY)).toBeNull())
  })

  it('shows a retry/clear error state (not an infinite spinner) on a non-404 failure', async () => {
    // A transient/server error settles the query with no data and no automatic
    // retry beyond the built-in 2 — without an explicit error branch this used
    // to render <Spinner/> forever (the "wheel of death" bug, vires-ops#40).
    vi.spyOn(api, 'getWorkout').mockRejectedValue(new Error('500: internal error'))
    renderWithProviders(<WorkoutPage />)
    // The query's own retry (2 retries, default backoff) runs before settling.
    expect(await screen.findByText("Couldn't load this workout", {}, { timeout: 5000 })).toBeInTheDocument()
    expect(screen.getByText('Retry')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Clear active workout'))
    await waitFor(() => expect(localStorage.getItem(ACTIVE_KEY)).toBeNull())
  })

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
    await waitFor(() =>
      expect(log).toHaveBeenCalledWith(10, 100, { reps: 8, weight: 135, done: false }),
    )
  })

  it('marks a set done and starts the rest timer', async () => {
    vi.spyOn(api, 'getWorkout').mockResolvedValue(makeSession())
    const upd = vi.spyOn(api, 'updateSet').mockResolvedValue(makeSet({ completed_at: '2026-06-28T18:05:00Z' }))
    renderWithProviders(<WorkoutPage />)
    await screen.findByText('Bench Press')
    fireEvent.click(screen.getByTitle('Mark done'))
    await waitFor(() => expect(upd).toHaveBeenCalled())
    expect(upd.mock.calls[0][3]).toMatchObject({ done: true })
    // rest timer bar appears
    expect(await screen.findByText('Rest')).toBeInTheDocument()
    expect(screen.getByText('Skip')).toBeInTheDocument()
  })

  it('skips the rest timer when the per-exercise toggle is off', async () => {
    localStorage.setItem('vires.restOn.100', '0')
    vi.spyOn(api, 'getWorkout').mockResolvedValue(makeSession())
    vi.spyOn(api, 'updateSet').mockResolvedValue(makeSet({ completed_at: '2026-06-28T18:05:00Z' }))
    renderWithProviders(<WorkoutPage />)
    await screen.findByText('Bench Press')
    expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(false)
    fireEvent.click(screen.getByTitle('Mark done'))
    await waitFor(() => expect(api.updateSet).toHaveBeenCalled())
    // no rest bar appears because the timer is disabled for this exercise
    expect(screen.queryByText('Rest')).not.toBeInTheDocument()
    localStorage.removeItem('vires.restOn.100')
  })

  it('reorders exercises by swapping order_index with a neighbour', async () => {
    const a = makeSessionExercise({ id: 100, order_index: 0, exercise: makeBrief({ name: 'Bench Press' }) })
    const b = makeSessionExercise({ id: 101, order_index: 1, exercise: makeBrief({ id: 2, name: 'Squat' }) })
    vi.spyOn(api, 'getWorkout').mockResolvedValue(makeSession({ exercises: [a, b] }))
    const upd = vi.spyOn(api, 'updateWorkoutExercise').mockResolvedValue(a)
    renderWithProviders(<WorkoutPage />)
    await screen.findByText('Squat')
    // the first exercise can move down; the second can move up
    fireEvent.click(screen.getAllByTitle('Move down')[0])
    await waitFor(() => expect(upd).toHaveBeenCalledTimes(2))
    expect(upd).toHaveBeenCalledWith(10, 100, { order_index: 1 })
    expect(upd).toHaveBeenCalledWith(10, 101, { order_index: 0 })
  })

  it('edits the rest duration ad hoc', async () => {
    vi.spyOn(api, 'getWorkout').mockResolvedValue(makeSession())
    const upd = vi.spyOn(api, 'updateWorkoutExercise').mockResolvedValue(makeSessionExercise())
    renderWithProviders(<WorkoutPage />)
    const rest = await screen.findByDisplayValue('90') // rest_seconds seeded at 90
    fireEvent.change(rest, { target: { value: '120' } })
    fireEvent.blur(rest)
    await waitFor(() => expect(upd).toHaveBeenCalledWith(10, 100, { rest_seconds: 120 }))
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

  it('hides the weight column when its toggle is turned off', async () => {
    vi.spyOn(api, 'getWorkout').mockResolvedValue(makeSession())
    renderWithProviders(<WorkoutPage />)
    expect(await screen.findByDisplayValue('135')).toBeInTheDocument() // weight cell visible
    fireEvent.click(screen.getByRole('button', { name: 'Weight' }))
    expect(screen.queryByDisplayValue('135')).not.toBeInTheDocument()
    expect(localStorage.getItem('vires.col.weight.100')).toBe('0')
    localStorage.removeItem('vires.col.weight.100')
  })

  it('enables a hold timer on a rep exercise via the Timer toggle', async () => {
    vi.spyOn(api, 'getWorkout').mockResolvedValue(makeSession())
    renderWithProviders(<WorkoutPage />)
    await screen.findByText('Bench Press')
    expect(screen.queryByTitle('Start hold')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Timer' }))
    expect(screen.getByTitle('Start hold')).toBeInTheDocument()
    expect(localStorage.getItem('vires.col.timer.100')).toBe('1')
    localStorage.removeItem('vires.col.timer.100')
  })

  it('exposes an editable seconds field on the running rest bar', async () => {
    vi.spyOn(api, 'getWorkout').mockResolvedValue(makeSession())
    vi.spyOn(api, 'updateSet').mockResolvedValue(makeSet({ completed_at: '2026-06-28T18:05:00Z' }))
    renderWithProviders(<WorkoutPage />)
    await screen.findByText('Bench Press')
    fireEvent.click(screen.getByTitle('Mark done'))
    await screen.findByText('Rest')
    const secs = screen.getByLabelText('Set timer seconds') as HTMLInputElement
    expect(secs.value).toBe('90') // seeded from the rest duration
    fireEvent.change(secs, { target: { value: '45' } })
    fireEvent.blur(secs)
    expect(secs.value).toBe('45')
  })

  it('renders the rest bar directly beneath the set that triggered it', async () => {
    const se = makeSessionExercise({
      sets: [makeSet({ id: 1000, set_number: 1 }), makeSet({ id: 1001, set_number: 2 })],
    })
    vi.spyOn(api, 'getWorkout').mockResolvedValue(makeSession({ exercises: [se] }))
    vi.spyOn(api, 'updateSet').mockResolvedValue(makeSet({ completed_at: '2026-06-28T18:05:00Z' }))
    renderWithProviders(<WorkoutPage />)
    await screen.findByText('Bench Press')
    fireEvent.click(screen.getAllByTitle('Mark done')[0]) // complete the first set
    const restBar = await screen.findByText('Rest')
    const set1 = screen.getByRole('button', { name: '1' })
    const set2 = screen.getByRole('button', { name: '2' })
    // bar sits after set 1 and before set 2
    expect(set1.compareDocumentPosition(restBar) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(restBar.compareDocumentPosition(set2) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
})
