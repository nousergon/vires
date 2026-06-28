import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import { renderWithProviders, makeHit } from '../test/utils'
import ExercisesPage from './ExercisesPage'
import { api } from '../lib/api'

beforeEach(() => vi.restoreAllMocks())

describe('ExercisesPage', () => {
  it('shows the prompt before any query', async () => {
    renderWithProviders(<ExercisesPage />)
    expect(await screen.findByText('Search the exercise library')).toBeInTheDocument()
  })

  it('searches and renders results with provenance + aliases', async () => {
    vi.spyOn(api, 'searchExercises').mockResolvedValue([
      makeHit({ id: 3, name: 'RDL', provenance: 'user', aliases: ['Romanian Deadlift'], mechanic: 'compound' }),
    ])
    renderWithProviders(<ExercisesPage />)
    fireEvent.change(screen.getByPlaceholderText(/Search/), { target: { value: 'rdl' } })
    expect(await screen.findByText('RDL')).toBeInTheDocument()
    expect(screen.getByText('user')).toBeInTheDocument() // non-canonical provenance badge
    expect(screen.getByText(/aka Romanian Deadlift/)).toBeInTheDocument()
  })

  it('shows a no-matches state', async () => {
    vi.spyOn(api, 'searchExercises').mockResolvedValue([])
    renderWithProviders(<ExercisesPage />)
    fireEvent.change(screen.getByPlaceholderText(/Search/), { target: { value: 'zzzz' } })
    expect(await screen.findByText('No matches')).toBeInTheDocument()
  })

  it('opens the new-exercise picker', async () => {
    renderWithProviders(<ExercisesPage />)
    fireEvent.click(screen.getByText('New'))
    expect(await screen.findByText('Add exercise')).toBeInTheDocument()
  })
})
