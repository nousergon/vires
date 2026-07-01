import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderWithProviders, SETTINGS, makeSession } from '../test/utils'
import { api } from '../lib/api'
import RuckForm from './RuckForm'

beforeEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
  vi.spyOn(api, 'getSettings').mockResolvedValue(SETTINGS) // weight_unit: 'lb'
})

function ruckResult(cost: number | null) {
  return makeSession({
    id: 1,
    session_type: 'ruck',
    name: 'Ruck',
    ended_at: '2026-06-28T18:00:00Z',
    exercises: [],
    ruck: {
      pack_weight_kg: 20.4,
      bodyweight_kg: 81.6,
      distance_m: 4828,
      elevation_gain_m: 305,
      duration_s: 3600,
      terrain: 'trail',
      metabolic_cost_kj: cost,
      source: 'manual',
    },
  })
}

describe('RuckForm', () => {
  it('logs a ruck with the entered values and shows the computed load', async () => {
    const log = vi.spyOn(api, 'logRuck').mockResolvedValue(ruckResult(4184))
    renderWithProviders(<RuckForm open onClose={() => {}} />)

    // Labels reflect the account's lb unit (⇒ miles / feet).
    expect(await screen.findByText(/Pack weight \(lb\)/)).toBeInTheDocument()
    expect(screen.getByText(/Distance \(mi\)/)).toBeInTheDocument()

    // Pack + bodyweight are the first two numeric fields.
    const [packInput, bodyInput] = screen.getAllByRole('spinbutton')
    fireEvent.change(packInput, { target: { value: '45' } })
    fireEvent.change(bodyInput, { target: { value: '180' } })

    fireEvent.click(screen.getByText('Log ruck'))

    await waitFor(() => expect(log).toHaveBeenCalledTimes(1))
    expect(log.mock.calls[0][0]).toMatchObject({ pack_weight: 45, bodyweight: 180, terrain: 'trail' })
    // Success view surfaces the load (4184 kJ → 1,000 kcal).
    expect(await screen.findByText(/1,000 kcal/)).toBeInTheDocument()
  })

  it('shows a nudge instead of a load when distance/time are omitted', async () => {
    vi.spyOn(api, 'logRuck').mockResolvedValue(ruckResult(null))
    renderWithProviders(<RuckForm open onClose={() => {}} />)

    const [pack, body] = await screen.findAllByRole('spinbutton')
    fireEvent.change(pack, { target: { value: '40' } })
    fireEvent.change(body, { target: { value: '175' } })
    fireEvent.click(screen.getByText('Log ruck'))

    expect(await screen.findByText(/Add distance \+ time/)).toBeInTheDocument()
  })

  it('remembers pack + bodyweight for next time', async () => {
    vi.spyOn(api, 'logRuck').mockResolvedValue(ruckResult(4184))
    renderWithProviders(<RuckForm open onClose={() => {}} />)
    const [pack, body] = await screen.findAllByRole('spinbutton')
    fireEvent.change(pack, { target: { value: '45' } })
    fireEvent.change(body, { target: { value: '180' } })
    fireEvent.click(screen.getByText('Log ruck'))
    await waitFor(() => expect(localStorage.getItem('vires.ruck.lastPack')).toBe('45'))
    expect(localStorage.getItem('vires.ruck.lastBody')).toBe('180')
  })
})
