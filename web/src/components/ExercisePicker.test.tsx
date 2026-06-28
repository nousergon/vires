import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderWithProviders, makeExercise, makeHit } from '../test/utils'
import ExercisePicker from './ExercisePicker'
import { api } from '../lib/api'

beforeEach(() => vi.restoreAllMocks())

describe('ExercisePicker', () => {
  it('searches and selects an existing exercise', async () => {
    vi.spyOn(api, 'searchExercises').mockResolvedValue([makeHit({ id: 3, name: 'Romanian Deadlift' })])
    const onSelect = vi.fn()
    const onClose = vi.fn()
    renderWithProviders(<ExercisePicker open onClose={onClose} onSelect={onSelect} />)
    fireEvent.change(screen.getByPlaceholderText(/Search/), { target: { value: 'rdl' } })
    fireEvent.click(await screen.findByText('Romanian Deadlift'))
    expect(onSelect).toHaveBeenCalledTimes(1)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('creates a brand-new exercise when nothing matches', async () => {
    vi.spyOn(api, 'searchExercises').mockResolvedValue([])
    const create = vi.spyOn(api, 'createExercise').mockResolvedValue({
      created: true,
      reason: 'created',
      exercise: makeExercise({ id: 9, name: 'Jefferson Curl' }),
      duplicate_of: null,
      similarity: null,
    })
    const onSelect = vi.fn()
    renderWithProviders(<ExercisePicker open onClose={() => {}} onSelect={onSelect} />)
    fireEvent.change(screen.getByPlaceholderText(/Search/), { target: { value: 'Jefferson Curl' } })
    fireEvent.click(await screen.findByRole('button', { name: /Add .* as a new exercise/i }))
    await waitFor(() => expect(create).toHaveBeenCalledWith({ name: 'Jefferson Curl', force: false }))
    await waitFor(() => expect(onSelect).toHaveBeenCalled())
  })

  it('surfaces a duplicate suggestion and lets you use it', async () => {
    vi.spyOn(api, 'searchExercises').mockResolvedValue([])
    const dup = makeExercise({ id: 1, name: 'Bench Press' })
    vi.spyOn(api, 'createExercise').mockResolvedValue({
      created: false,
      reason: 'exact',
      exercise: null,
      duplicate_of: dup,
      similarity: 1,
    })
    const onSelect = vi.fn()
    renderWithProviders(<ExercisePicker open onClose={() => {}} onSelect={onSelect} />)
    fireEvent.change(screen.getByPlaceholderText(/Search/), { target: { value: 'bench' } })
    fireEvent.click(await screen.findByRole('button', { name: /Add .* as a new exercise/i }))
    expect(await screen.findByText('Already in your library:')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Use it'))
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 1, name: 'Bench Press' }))
  })
})
