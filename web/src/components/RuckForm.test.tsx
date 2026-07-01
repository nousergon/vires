import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderWithProviders, SETTINGS, makeSession } from '../test/utils'
import { api } from '../lib/api'
import RuckForm from './RuckForm'

// The Leaflet map is browser-only (WebGL/DOM); stub it so the draw-mode flow is
// testable — the stub adds two waypoints via the real onAddPoint callback.
vi.mock('./RouteDrawMap', () => ({
  default: ({ onAddPoint }: { onAddPoint: (lat: number, lon: number) => void }) => (
    <button
      onClick={() => {
        onAddPoint(47.6, -121.6)
        onAddPoint(47.62, -121.6)
      }}
    >
      stub-add-2-points
    </button>
  ),
}))

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

  it('trail search fills distance/elevation and logs source route_search', async () => {
    vi.spyOn(api, 'searchTrails').mockResolvedValue({
      candidates: [
        { osm_id: 42, name: 'Mailbox Peak Trail', distance_m: 8046,
          points: [{ lat: 47.6, lon: -121.6 }, { lat: 47.62, lon: -121.6 }] },
      ],
    })
    // 8046 m ⇒ 5 mi, 305 m ⇒ ~1000 ft.
    vi.spyOn(api, 'measureRoute').mockResolvedValue({
      distance_m: 8046, elevation_gain_m: 305, point_count: 2, duration_s: null,
    })
    const log = vi.spyOn(api, 'logRuck').mockResolvedValue(ruckResult(4184))
    renderWithProviders(<RuckForm open onClose={() => {}} />)

    const [pack, body] = await screen.findAllByRole('spinbutton')
    fireEvent.change(pack, { target: { value: '45' } })
    fireEvent.change(body, { target: { value: '180' } })
    fireEvent.click(screen.getByText('Search'))
    fireEvent.change(screen.getByLabelText('trail name'), { target: { value: 'Mailbox Peak' } })
    fireEvent.click(screen.getByText('Find'))
    fireEvent.click(await screen.findByText('Mailbox Peak Trail'))

    // Distance field (3rd spinbutton: pack, body, distance) auto-fills to 5 mi.
    await waitFor(() =>
      expect((screen.getAllByRole('spinbutton')[2] as HTMLInputElement).value).toBe('5'),
    )
    fireEvent.click(screen.getByText('Log ruck'))
    await waitFor(() => expect(log).toHaveBeenCalled())
    expect(log.mock.calls[0][0].source).toBe('route_search')
  })

  it('draw-on-map measures the traced route and logs source route_draw', async () => {
    const measure = vi.spyOn(api, 'measureRoute').mockResolvedValue({
      distance_m: 8046, elevation_gain_m: 305, point_count: 2, duration_s: null,
    })
    const log = vi.spyOn(api, 'logRuck').mockResolvedValue(ruckResult(4184))
    renderWithProviders(<RuckForm open onClose={() => {}} />)

    const [pack, body] = await screen.findAllByRole('spinbutton')
    fireEvent.change(pack, { target: { value: '45' } })
    fireEvent.change(body, { target: { value: '180' } })
    fireEvent.click(screen.getByText('Draw'))
    // The mocked map stub drops two waypoints when clicked.
    fireEvent.click(screen.getByText('stub-add-2-points'))
    fireEvent.click(screen.getByText(/Measure route \(2 pts\)/))

    await waitFor(() => expect(measure).toHaveBeenCalledTimes(1))
    expect(measure.mock.calls[0][0]).toHaveLength(2)
    await waitFor(() =>
      expect((screen.getAllByRole('spinbutton')[2] as HTMLInputElement).value).toBe('5'),
    )
    fireEvent.click(screen.getByText('Log ruck'))
    await waitFor(() => expect(log).toHaveBeenCalled())
    expect(log.mock.calls[0][0].source).toBe('route_draw')
  })

  it('gpx import fills distance + duration and logs source gpx', async () => {
    vi.spyOn(api, 'importGpx').mockResolvedValue({
      distance_m: 8046, elevation_gain_m: 305, point_count: 100, duration_s: 7200,
    })
    const log = vi.spyOn(api, 'logRuck').mockResolvedValue(ruckResult(4184))
    renderWithProviders(<RuckForm open onClose={() => {}} />)

    const [pack, body] = await screen.findAllByRole('spinbutton')
    fireEvent.change(pack, { target: { value: '45' } })
    fireEvent.change(body, { target: { value: '180' } })
    fireEvent.click(screen.getByText('GPX'))
    const file = new File(['<gpx></gpx>'], 'hike.gpx', { type: 'application/gpx+xml' })
    fireEvent.change(screen.getByLabelText('gpx file'), { target: { files: [file] } })

    // 8046 m ⇒ 5 mi distance; 7200 s ⇒ 2h.
    await waitFor(() =>
      expect((screen.getAllByRole('spinbutton')[2] as HTMLInputElement).value).toBe('5'),
    )
    expect((screen.getAllByRole('spinbutton')[4] as HTMLInputElement).value).toBe('2') // hours
    fireEvent.click(screen.getByText('Log ruck'))
    await waitFor(() => expect(log).toHaveBeenCalled())
    expect(log.mock.calls[0][0].source).toBe('gpx')
  })
})
