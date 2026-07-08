import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderWithProviders, makeObjective, makeActiveObjective } from '../test/utils'
import ObjectiveSheet from './ObjectiveSheet'
import { api } from '../lib/api'

beforeEach(() => vi.restoreAllMocks())

const OBJECTIVE = makeObjective({ id: 1, name: 'Climb Baker', is_primary: true })

describe('ObjectiveSheet', () => {
  it('creates a NEW non-primary objective from the form (no objectiveId)', async () => {
    vi.spyOn(api, 'activeObjective').mockResolvedValue(makeActiveObjective())
    vi.spyOn(api, 'listObjectives').mockResolvedValue([])
    const create = vi.spyOn(api, 'createObjective').mockResolvedValue(OBJECTIVE)
    renderWithProviders(<ObjectiveSheet open onClose={() => {}} onSaved={() => {}} />)

    fireEvent.change(await screen.findByPlaceholderText('e.g. Climb Baker'), {
      target: { value: 'Climb Baker' },
    })
    // dated is the default; fill the target date (first date input)
    const dateInput = document.querySelector('input[type="date"]') as HTMLInputElement
    fireEvent.change(dateInput, { target: { value: '2026-09-05' } })

    fireEvent.click(screen.getByText('Add objective'))
    await waitFor(() =>
      expect(create).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Climb Baker',
          kind: 'dated',
          target_date: '2026-09-05',
          is_primary: false, // not pinned -> let the focus be derived
        }),
      ),
    )
  })

  it('closes the sheet after a successful save (prevents a stale-form double submit)', async () => {
    vi.spyOn(api, 'activeObjective').mockResolvedValue(makeActiveObjective())
    vi.spyOn(api, 'listObjectives').mockResolvedValue([])
    const create = vi.spyOn(api, 'createObjective').mockResolvedValue(OBJECTIVE)
    const onClose = vi.fn()
    renderWithProviders(<ObjectiveSheet open onClose={onClose} onSaved={() => {}} />)

    fireEvent.change(await screen.findByPlaceholderText('e.g. Climb Baker'), {
      target: { value: 'Climb Kangaroo Temple' },
    })
    const dateInput = document.querySelector('input[type="date"]') as HTMLInputElement
    fireEvent.change(dateInput, { target: { value: '2026-08-01' } })

    fireEvent.click(screen.getByText('Add objective'))
    await waitFor(() => expect(create).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
  })

  it('pin-as-focus sends is_primary: true', async () => {
    vi.spyOn(api, 'activeObjective').mockResolvedValue(makeActiveObjective())
    vi.spyOn(api, 'listObjectives').mockResolvedValue([])
    const create = vi.spyOn(api, 'createObjective').mockResolvedValue(OBJECTIVE)
    renderWithProviders(<ObjectiveSheet open onClose={() => {}} onSaved={() => {}} />)

    fireEvent.change(await screen.findByPlaceholderText('e.g. Climb Baker'), {
      target: { value: 'Climb Baker' },
    })
    const dateInput = document.querySelector('input[type="date"]') as HTMLInputElement
    fireEvent.change(dateInput, { target: { value: '2026-09-05' } })
    fireEvent.click(screen.getByText(/Pin as my focus/))
    fireEvent.click(screen.getByText('Add objective'))
    await waitFor(() =>
      expect(create).toHaveBeenCalledWith(expect.objectContaining({ is_primary: true })),
    )
  })

  it('disables save for a dated objective with no date', async () => {
    vi.spyOn(api, 'activeObjective').mockResolvedValue(makeActiveObjective())
    vi.spyOn(api, 'listObjectives').mockResolvedValue([])
    renderWithProviders(<ObjectiveSheet open onClose={() => {}} onSaved={() => {}} />)
    fireEvent.change(await screen.findByPlaceholderText('e.g. Climb Baker'), {
      target: { value: 'Climb Baker' },
    })
    expect((screen.getByText('Add objective') as HTMLButtonElement).disabled).toBe(true)
  })

  it('edits a specific objective (by objectiveId) and prefills the form', async () => {
    vi.spyOn(api, 'activeObjective').mockResolvedValue(makeActiveObjective({ objective: OBJECTIVE }))
    vi.spyOn(api, 'listObjectives').mockResolvedValue([OBJECTIVE])
    const update = vi.spyOn(api, 'updateObjective').mockResolvedValue(OBJECTIVE)
    renderWithProviders(<ObjectiveSheet open objectiveId={1} onClose={() => {}} onSaved={() => {}} />)

    expect((await screen.findByDisplayValue('Climb Baker')).getAttribute('value')).toBe('Climb Baker')
    fireEvent.click(screen.getByText('Update objective'))
    await waitFor(() =>
      expect(update).toHaveBeenCalledWith(1, expect.objectContaining({ name: 'Climb Baker' })),
    )
  })

  it('surfaces priority + event window when editing', async () => {
    const withWindow = makeObjective({
      id: 1,
      priority: 3,
      event_end_date: '2026-09-07',
    })
    vi.spyOn(api, 'activeObjective').mockResolvedValue(makeActiveObjective({ objective: withWindow }))
    vi.spyOn(api, 'listObjectives').mockResolvedValue([withWindow])
    renderWithProviders(<ObjectiveSheet open objectiveId={1} onClose={() => {}} onSaved={() => {}} />)
    expect(await screen.findByDisplayValue('3')).toBeInTheDocument() // priority
    expect(screen.getByDisplayValue('2026-09-07')).toBeInTheDocument() // event end
  })

  it('adds a constraint', async () => {
    vi.spyOn(api, 'activeObjective').mockResolvedValue(makeActiveObjective({ objective: OBJECTIVE }))
    vi.spyOn(api, 'listObjectives').mockResolvedValue([OBJECTIVE])
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
    renderWithProviders(<ObjectiveSheet open objectiveId={1} onClose={() => {}} onSaved={() => {}} />)

    // Two "+ Add" buttons (milestones + constraints); constraints is rendered last.
    const addButtons = await screen.findAllByText('+ Add')
    fireEvent.click(addButtons[addButtons.length - 1])
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

  it('adds a training milestone nested under the edited objective', async () => {
    vi.spyOn(api, 'activeObjective').mockResolvedValue(makeActiveObjective({ objective: OBJECTIVE }))
    vi.spyOn(api, 'listObjectives').mockResolvedValue([OBJECTIVE])
    const addM = vi.spyOn(api, 'createObjective').mockResolvedValue(
      makeObjective({ id: 5, name: 'Mailbox Peak', target_date: '2026-08-01', parent_objective_id: 1 }),
    )
    renderWithProviders(<ObjectiveSheet open objectiveId={1} onClose={() => {}} onSaved={() => {}} />)

    // The milestones section's "+ Add" is first (rendered before constraints).
    const addButtons = await screen.findAllByText('+ Add')
    fireEvent.click(addButtons[0])
    fireEvent.change(screen.getByPlaceholderText(/Mailbox Peak/), {
      target: { value: 'Mailbox Peak' },
    })
    // Multiple date inputs now (objective target + event end + milestone); the
    // milestone's is rendered last.
    const dateInputs = document.querySelectorAll('input[type="date"]')
    fireEvent.change(dateInputs[dateInputs.length - 1], { target: { value: '2026-08-01' } })
    fireEvent.click(screen.getByText('Add milestone'))

    await waitFor(() =>
      expect(addM).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Mailbox Peak',
          kind: 'dated',
          target_date: '2026-08-01',
          is_primary: false,
          parent_objective_id: 1,
        }),
      ),
    )
  })

  it('renders existing milestones (derived from listObjectives) under the objective', async () => {
    const milestone = makeObjective({
      id: 5,
      name: 'Mailbox Peak',
      target_date: '2026-08-01',
      is_primary: false,
      parent_objective_id: 1,
    })
    vi.spyOn(api, 'activeObjective').mockResolvedValue(makeActiveObjective({ objective: OBJECTIVE }))
    vi.spyOn(api, 'listObjectives').mockResolvedValue([OBJECTIVE, milestone])
    renderWithProviders(<ObjectiveSheet open objectiveId={1} onClose={() => {}} onSaved={() => {}} />)
    expect(await screen.findByText('Training milestones')).toBeInTheDocument()
    expect(screen.getByText('Mailbox Peak')).toBeInTheDocument()
  })
})
