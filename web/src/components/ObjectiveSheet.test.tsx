import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderWithProviders } from '../test/utils'
import ObjectiveSheet from './ObjectiveSheet'
import { api, type ActiveObjective, type Objective } from '../lib/api'

beforeEach(() => vi.restoreAllMocks())

const EMPTY: ActiveObjective = { objective: null, constraints: [] }

const OBJECTIVE: Objective = {
  id: 1,
  name: 'Climb Baker',
  kind: 'dated',
  target_date: '2026-09-05',
  sport: 'alpine',
  demands_profile: null,
  is_primary: true,
  created_at: '',
  updated_at: '',
}

describe('ObjectiveSheet', () => {
  it('creates a primary objective from the form', async () => {
    vi.spyOn(api, 'activeObjective').mockResolvedValue(EMPTY)
    const create = vi.spyOn(api, 'createObjective').mockResolvedValue(OBJECTIVE)
    renderWithProviders(<ObjectiveSheet open onClose={() => {}} onSaved={() => {}} />)

    fireEvent.change(await screen.findByPlaceholderText('e.g. Climb Baker'), {
      target: { value: 'Climb Baker' },
    })
    // dated is the default; fill the date
    const dateInput = document.querySelector('input[type="date"]') as HTMLInputElement
    fireEvent.change(dateInput, { target: { value: '2026-09-05' } })

    fireEvent.click(screen.getByText('Set objective'))
    await waitFor(() =>
      expect(create).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Climb Baker',
          kind: 'dated',
          target_date: '2026-09-05',
          is_primary: true,
        }),
      ),
    )
  })

  it('disables save for a dated objective with no date', async () => {
    vi.spyOn(api, 'activeObjective').mockResolvedValue(EMPTY)
    renderWithProviders(<ObjectiveSheet open onClose={() => {}} onSaved={() => {}} />)
    fireEvent.change(await screen.findByPlaceholderText('e.g. Climb Baker'), {
      target: { value: 'Climb Baker' },
    })
    expect((screen.getByText('Set objective') as HTMLButtonElement).disabled).toBe(true)
  })

  it('updates an existing objective and prefills the form', async () => {
    vi.spyOn(api, 'activeObjective').mockResolvedValue({ objective: OBJECTIVE, constraints: [] })
    const update = vi.spyOn(api, 'updateObjective').mockResolvedValue(OBJECTIVE)
    renderWithProviders(<ObjectiveSheet open onClose={() => {}} onSaved={() => {}} />)

    // prefilled name
    expect((await screen.findByDisplayValue('Climb Baker')).getAttribute('value')).toBe('Climb Baker')
    fireEvent.click(screen.getByText('Update objective'))
    await waitFor(() => expect(update).toHaveBeenCalledWith(1, expect.objectContaining({ is_primary: true })))
  })

  it('adds a constraint', async () => {
    vi.spyOn(api, 'activeObjective').mockResolvedValue({ objective: OBJECTIVE, constraints: [] })
    const addC = vi.spyOn(api, 'createConstraint').mockResolvedValue({
      id: 9,
      kind: 'injury',
      label: 'recovering L4-L5 disc',
      directives: null,
      defer_to_professional: true,
      is_active: true,
      created_at: '',
      updated_at: '',
    })
    renderWithProviders(<ObjectiveSheet open onClose={() => {}} onSaved={() => {}} />)

    fireEvent.click(await screen.findByText('+ Add'))
    fireEvent.change(screen.getByPlaceholderText(/recovering L4-L5 disc/), {
      target: { value: 'recovering L4-L5 disc' },
    })
    fireEvent.click(screen.getByText('Add constraint'))
    await waitFor(() =>
      expect(addC).toHaveBeenCalledWith(
        expect.objectContaining({ kind: 'injury', label: 'recovering L4-L5 disc' }),
      ),
    )
  })
})
