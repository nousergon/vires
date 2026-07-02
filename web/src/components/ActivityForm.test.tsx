import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderWithProviders, SETTINGS, makeSession } from '../test/utils'
import { api, type ActivityTemplate } from '../lib/api'
import ActivityForm from './ActivityForm'

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(api, 'getSettings').mockResolvedValue(SETTINGS)
})

const TEMPLATES: ActivityTemplate[] = [
  { key: 'climbing_indoor_toprope', label: 'Indoor top-rope', regions: 'upper', intensity: 'moderate' },
  { key: 'swimming', label: 'Swimming', regions: 'full', intensity: 'moderate' },
]

function activityResult(name: string) {
  return makeSession({
    id: 1,
    session_type: 'activity',
    name,
    exercises: [],
    ruck: null,
    activity: { template_key: 'custom', duration_s: null, regions: 'full', intensity: 'moderate' },
  })
}

describe('ActivityForm', () => {
  it('picking a template prefills name/regions/intensity and logs it', async () => {
    vi.spyOn(api, 'listActivityTemplates').mockResolvedValue(TEMPLATES)
    const log = vi.spyOn(api, 'logActivity').mockResolvedValue(activityResult('Indoor top-rope'))
    renderWithProviders(<ActivityForm open onClose={() => {}} />)

    fireEvent.click(await screen.findByText('Indoor top-rope'))
    expect((screen.getByPlaceholderText('e.g. Ultimate frisbee') as HTMLInputElement).value).toBe(
      'Indoor top-rope',
    )
    fireEvent.click(screen.getByText('Log activity'))

    await waitFor(() => expect(log).toHaveBeenCalledTimes(1))
    expect(log.mock.calls[0][0]).toMatchObject({
      name: 'Indoor top-rope',
      template_key: 'climbing_indoor_toprope',
      regions: 'upper',
      intensity: 'moderate',
    })
    expect(await screen.findByText('Indoor top-rope logged.')).toBeInTheDocument()
  })

  it('logs a custom freeform activity with manually chosen regions/intensity', async () => {
    vi.spyOn(api, 'listActivityTemplates').mockResolvedValue(TEMPLATES)
    const log = vi.spyOn(api, 'logActivity').mockResolvedValue(activityResult('Ultimate frisbee'))
    renderWithProviders(<ActivityForm open onClose={() => {}} />)

    await screen.findByText('Custom') // templates loaded
    fireEvent.change(screen.getByPlaceholderText('e.g. Ultimate frisbee'), {
      target: { value: 'Ultimate frisbee' },
    })
    fireEvent.click(screen.getByText('Legs'))
    fireEvent.click(screen.getByText('Hard'))
    fireEvent.click(screen.getByText('Log activity'))

    await waitFor(() => expect(log).toHaveBeenCalledTimes(1))
    expect(log.mock.calls[0][0]).toMatchObject({
      name: 'Ultimate frisbee',
      template_key: 'custom',
      regions: 'legs',
      intensity: 'hard',
    })
  })

  it('disables submit until a name is entered', async () => {
    vi.spyOn(api, 'listActivityTemplates').mockResolvedValue(TEMPLATES)
    renderWithProviders(<ActivityForm open onClose={() => {}} />)
    await screen.findByText('Custom')
    expect(screen.getByText('Log activity')).toBeDisabled()
    fireEvent.change(screen.getByPlaceholderText('e.g. Ultimate frisbee'), {
      target: { value: 'Something' },
    })
    expect(screen.getByText('Log activity')).not.toBeDisabled()
  })

  it('backdates started_at when a past date is chosen', async () => {
    vi.spyOn(api, 'listActivityTemplates').mockResolvedValue(TEMPLATES)
    const log = vi.spyOn(api, 'logActivity').mockResolvedValue(activityResult('Yoga'))
    renderWithProviders(<ActivityForm open onClose={() => {}} />)

    await screen.findByText('Custom')
    const dateInput = document.querySelector('input[type="date"]') as HTMLInputElement
    fireEvent.change(dateInput, { target: { value: '2026-06-15' } })
    fireEvent.change(screen.getByPlaceholderText('e.g. Ultimate frisbee'), {
      target: { value: 'Yoga' },
    })
    fireEvent.click(screen.getByText('Log activity'))

    await waitFor(() => expect(log).toHaveBeenCalledTimes(1))
    const startedAt = log.mock.calls[0][0].started_at!
    expect(new Date(startedAt).getFullYear()).toBe(2026)
    expect(new Date(startedAt).getMonth()).toBe(5) // June (0-indexed)
    expect(new Date(startedAt).getDate()).toBe(15)
  })
})
