import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderWithProviders } from '../test/utils'
import CalendarEventSheet from './CalendarEventSheet'
import { api, type CalendarEvent } from '../lib/api'

beforeEach(() => vi.restoreAllMocks())

function makeEvent(over: Partial<CalendarEvent> = {}): CalendarEvent {
  return {
    id: 1,
    name: 'Tuesday league game',
    sport: 'soccer',
    type: 'league',
    event_date: '2026-07-07',
    event_end_date: null,
    recurrence: 'weekly',
    load: { regions: 'legs', intensity: 'hard', duration_min: 90 },
    notes: null,
    objective_id: null,
    created_at: '',
    updated_at: '',
    ...over,
  }
}

describe('CalendarEventSheet', () => {
  it('creates a new one-off event with load tagging', async () => {
    vi.spyOn(api, 'listCalendarEvents').mockResolvedValue([])
    const create = vi.spyOn(api, 'createCalendarEvent').mockResolvedValue(makeEvent())
    renderWithProviders(
      <CalendarEventSheet open onClose={() => {}} onSaved={() => {}} />,
    )

    fireEvent.change(await screen.findByPlaceholderText('e.g. Tuesday league game'), {
      target: { value: 'Regional 5k' },
    })
    const dateInput = document.querySelector('input[type="date"]') as HTMLInputElement
    fireEvent.change(dateInput, { target: { value: '2026-08-01' } })
    fireEvent.click(screen.getByText('Tag training load'))
    fireEvent.click(screen.getByText('Add event'))

    await waitFor(() =>
      expect(create).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Regional 5k',
          type: 'competition',
          event_date: '2026-08-01',
          recurrence: 'none',
          load: { regions: 'full', intensity: 'moderate', duration_min: null },
        }),
      ),
    )
  })

  it('sends recurrence: weekly when the toggle is on and omits event_end_date', async () => {
    vi.spyOn(api, 'listCalendarEvents').mockResolvedValue([])
    const create = vi.spyOn(api, 'createCalendarEvent').mockResolvedValue(makeEvent())
    renderWithProviders(
      <CalendarEventSheet open onClose={() => {}} onSaved={() => {}} />,
    )

    fireEvent.change(await screen.findByPlaceholderText('e.g. Tuesday league game'), {
      target: { value: 'Weekly pickup game' },
    })
    const dateInput = document.querySelector('input[type="date"]') as HTMLInputElement
    fireEvent.change(dateInput, { target: { value: '2026-07-07' } })
    fireEvent.click(screen.getByText('Repeats weekly'))
    fireEvent.click(screen.getByText('Add event'))

    await waitFor(() =>
      expect(create).toHaveBeenCalledWith(
        expect.objectContaining({ recurrence: 'weekly', event_end_date: null }),
      ),
    )
  })

  it('disables save with no name or date', async () => {
    vi.spyOn(api, 'listCalendarEvents').mockResolvedValue([])
    renderWithProviders(
      <CalendarEventSheet open onClose={() => {}} onSaved={() => {}} />,
    )
    expect((await screen.findByText('Add event')) as HTMLButtonElement).toBeDisabled()
  })

  it('edits an existing event and prefills the form', async () => {
    const existing = makeEvent()
    vi.spyOn(api, 'listCalendarEvents').mockResolvedValue([existing])
    const update = vi.spyOn(api, 'updateCalendarEvent').mockResolvedValue(existing)
    renderWithProviders(
      <CalendarEventSheet open eventId={1} onClose={() => {}} onSaved={() => {}} />,
    )

    expect(await screen.findByDisplayValue('Tuesday league game')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Update event'))
    await waitFor(() =>
      expect(update).toHaveBeenCalledWith(1, expect.objectContaining({ name: 'Tuesday league game' })),
    )
  })

  it('deletes an existing event', async () => {
    const existing = makeEvent()
    vi.spyOn(api, 'listCalendarEvents').mockResolvedValue([existing])
    const del = vi.spyOn(api, 'deleteCalendarEvent').mockResolvedValue(undefined)
    const onSaved = vi.fn()
    renderWithProviders(
      <CalendarEventSheet open eventId={1} onClose={() => {}} onSaved={onSaved} />,
    )

    fireEvent.click(await screen.findByText('Delete event'))
    await waitFor(() => expect(del).toHaveBeenCalledWith(1))
    expect(onSaved).toHaveBeenCalled()
  })
})
