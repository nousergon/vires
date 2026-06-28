import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import {
  renderWithProviders,
  SETTINGS,
  makeBrief,
  makeHit,
  makeTemplate,
  makeTemplateSummary,
} from '../test/utils'
import TemplatesPage from './TemplatesPage'
import { api } from '../lib/api'

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(api, 'getSettings').mockResolvedValue(SETTINGS)
})

describe('TemplatesPage', () => {
  it('lists routines', async () => {
    vi.spyOn(api, 'listTemplates').mockResolvedValue([makeTemplateSummary({ name: 'Leg Day', exercise_count: 4 })])
    renderWithProviders(<TemplatesPage />)
    expect(await screen.findByText('Leg Day')).toBeInTheDocument()
    expect(screen.getByText('4 exercises')).toBeInTheDocument()
  })

  it('shows an empty state', async () => {
    vi.spyOn(api, 'listTemplates').mockResolvedValue([])
    renderWithProviders(<TemplatesPage />)
    expect(await screen.findByText('No routines yet')).toBeInTheDocument()
  })

  it('creates a new routine with an exercise', async () => {
    vi.spyOn(api, 'listTemplates').mockResolvedValue([])
    vi.spyOn(api, 'searchExercises').mockResolvedValue([makeHit({ id: 5, name: 'Squat', equipment: 'barbell' })])
    const create = vi.spyOn(api, 'createTemplate').mockResolvedValue(makeTemplate({ id: 2, name: 'Lower' }))
    renderWithProviders(<TemplatesPage />)
    fireEvent.click(await screen.findByText('New'))
    expect(await screen.findByText('New routine')).toBeInTheDocument()
    fireEvent.change(screen.getByPlaceholderText(/Routine name/), { target: { value: 'Lower' } })
    fireEvent.click(screen.getByText('+ Add exercise'))
    fireEvent.change(await screen.findByPlaceholderText(/Search/), { target: { value: 'squat' } })
    fireEvent.click(await screen.findByText('Squat'))
    expect(await screen.findByText('Squat')).toBeInTheDocument() // row added to the draft
    fireEvent.click(screen.getByText('Create routine'))
    await waitFor(() => expect(create).toHaveBeenCalled())
    expect(create.mock.calls[0][0]).toMatchObject({ name: 'Lower' })
    expect(create.mock.calls[0][0].exercises[0]).toMatchObject({ exercise_id: 5 })
  })

  it('opens an existing routine for editing', async () => {
    vi.spyOn(api, 'listTemplates').mockResolvedValue([makeTemplateSummary({ id: 3, name: 'Push' })])
    vi.spyOn(api, 'getTemplate').mockResolvedValue(
      makeTemplate({
        id: 3,
        name: 'Push',
        exercises: [
          {
            id: 1,
            order_index: 0,
            exercise: makeBrief({ name: 'Bench' }),
            target_sets: 3,
            target_reps: 8,
            target_weight: 135,
            target_duration_seconds: null,
            rest_seconds: 90,
            notes: null,
          },
        ],
      }),
    )
    renderWithProviders(<TemplatesPage />)
    fireEvent.click(await screen.findByText('Push'))
    expect(await screen.findByText('Edit routine')).toBeInTheDocument()
    expect(screen.getByText('Bench')).toBeInTheDocument()
    expect(screen.getByText('Save changes')).toBeInTheDocument()
  })

  it('deletes a routine after confirm', async () => {
    vi.spyOn(api, 'listTemplates').mockResolvedValue([makeTemplateSummary({ id: 3, name: 'Old' })])
    const del = vi.spyOn(api, 'deleteTemplate').mockResolvedValue(undefined as unknown as void)
    vi.stubGlobal('confirm', () => true)
    renderWithProviders(<TemplatesPage />)
    fireEvent.click(await screen.findByText('Delete'))
    await waitFor(() => expect(del).toHaveBeenCalledWith(3))
  })
})
