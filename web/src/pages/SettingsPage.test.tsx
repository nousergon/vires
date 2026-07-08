import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderWithProviders, SETTINGS } from '../test/utils'
import SettingsPage from './SettingsPage'
import { api } from '../lib/api'

beforeEach(() => vi.restoreAllMocks())

// Distinct rest value so the test can wait for settings to load (the page
// re-syncs its draft from the loaded settings, which would clobber an edit made
// before the load completes).
const LOADED = { ...SETTINGS, default_rest_seconds: 111 }

function mockApis() {
  vi.spyOn(api, 'getSettings').mockResolvedValue(LOADED)
  vi.spyOn(api, 'feedUrl').mockResolvedValue({ token: 'tok123', ics_path: '/api/plan/feed/tok123.ics' })
}

describe('SettingsPage', () => {
  it('changes the weight unit and saves', async () => {
    mockApis()
    const update = vi.spyOn(api, 'updateSettings').mockResolvedValue({ ...LOADED, weight_unit: 'kg' })
    renderWithProviders(<SettingsPage />)
    await screen.findByDisplayValue('111') // settings loaded
    fireEvent.click(screen.getByText('KG'))
    fireEvent.click(screen.getByText('Save settings'))
    await waitFor(() => expect(update).toHaveBeenCalled())
    expect(update.mock.calls[0][0]).toMatchObject({ weight_unit: 'kg' })
  })

  it('toggles a timer alert preference', async () => {
    mockApis()
    const update = vi.spyOn(api, 'updateSettings').mockResolvedValue(LOADED)
    renderWithProviders(<SettingsPage />)
    await screen.findByDisplayValue('111') // settings loaded
    expect(screen.getByText('Timer alerts')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Vibration')) // was on -> off
    fireEvent.click(screen.getByText('Save settings'))
    await waitFor(() => expect(update).toHaveBeenCalled())
    expect(update.mock.calls[0][0]).toMatchObject({ timer_vibration: false })
  })

  it('sets preferred training days and saves', async () => {
    mockApis()
    const update = vi.spyOn(api, 'updateSettings').mockResolvedValue(LOADED)
    renderWithProviders(<SettingsPage />)
    await screen.findByDisplayValue('111') // settings loaded
    expect(screen.getByText('Training schedule')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('monday'))
    fireEvent.click(screen.getByLabelText('thursday'))
    fireEvent.click(screen.getByText('Save settings'))
    await waitFor(() => expect(update).toHaveBeenCalled())
    expect(update.mock.calls[0][0]).toMatchObject({
      preferred_weekdays: ['monday', 'thursday'],
    })
  })

  it('toggling a selected day off removes it', async () => {
    mockApis()
    const update = vi.spyOn(api, 'updateSettings').mockResolvedValue(LOADED)
    renderWithProviders(<SettingsPage />)
    await screen.findByDisplayValue('111')
    fireEvent.click(screen.getByLabelText('monday'))
    fireEvent.click(screen.getByLabelText('monday')) // toggle back off
    fireEvent.click(screen.getByText('Save settings'))
    await waitFor(() => expect(update).toHaveBeenCalled())
    expect(update.mock.calls[0][0]).toMatchObject({ preferred_weekdays: [] })
  })

  it('renders the calendar-feed subscribe URL', async () => {
    mockApis()
    renderWithProviders(<SettingsPage />)
    expect(await screen.findByText(/feed\/tok123\.ics/)).toBeInTheDocument()
    expect(screen.getByText('Add to calendar')).toBeInTheDocument()
  })
})
