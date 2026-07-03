import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderWithProviders, SETTINGS, makeSession, makeActivityDetail } from '../test/utils'
import { api, type ActivityTemplate } from '../lib/api'
import ActivityForm from './ActivityForm'

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

const TEMPLATES: ActivityTemplate[] = [
  { key: 'walk', label: 'Walk', regions: 'legs', intensity: 'light', route_capable: true },
  { key: 'hike', label: 'Hike', regions: 'legs', intensity: 'moderate', route_capable: true },
  {
    key: 'climbing_indoor_toprope',
    label: 'Indoor top-rope',
    regions: 'upper',
    intensity: 'moderate',
    route_capable: false,
  },
  { key: 'swimming', label: 'Swimming', regions: 'full', intensity: 'moderate', route_capable: false },
]

function activityResult(name: string, over: Partial<ReturnType<typeof makeActivityDetail>> = {}) {
  return makeSession({
    id: 1,
    session_type: 'activity',
    name,
    exercises: [],
    activity: makeActivityDetail(over),
  })
}

describe('ActivityForm', () => {
  it('picking a non-route-capable template prefills name/regions/intensity, no route/pack UI', async () => {
    vi.spyOn(api, 'listActivityTemplates').mockResolvedValue(TEMPLATES)
    const log = vi.spyOn(api, 'logActivity').mockResolvedValue(activityResult('Indoor top-rope'))
    renderWithProviders(<ActivityForm open onClose={() => {}} />)

    fireEvent.click(await screen.findByText('Indoor top-rope'))
    expect((screen.getByPlaceholderText('e.g. Ultimate frisbee') as HTMLInputElement).value).toBe(
      'Indoor top-rope',
    )
    expect(screen.queryByText('Route')).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/Pack weight/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('Log activity'))

    await waitFor(() => expect(log).toHaveBeenCalledTimes(1))
    expect(log.mock.calls[0][0]).toMatchObject({
      name: 'Indoor top-rope',
      template_key: 'climbing_indoor_toprope',
      regions: 'upper',
      intensity: 'moderate',
    })
    expect(log.mock.calls[0][0].pack_weight).toBeUndefined()
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

  it('seeds the date from defaultDate (e.g. a tapped Plan-calendar day)', async () => {
    vi.spyOn(api, 'listActivityTemplates').mockResolvedValue(TEMPLATES)
    renderWithProviders(<ActivityForm open defaultDate="2026-07-10" onClose={() => {}} />)
    await screen.findByText('Custom')
    const dateInput = document.querySelector('input[type="date"]') as HTMLInputElement
    expect(dateInput.value).toBe('2026-07-10')
  })

  // ------------------------------------------------------------------------ //
  // Route-capable templates (walk/run/hike): route capture + optional pack.
  // ------------------------------------------------------------------------ //
  it('logs a route-capable activity with no pack — pack/bodyweight omitted entirely', async () => {
    vi.spyOn(api, 'listActivityTemplates').mockResolvedValue(TEMPLATES)
    const log = vi.spyOn(api, 'logActivity').mockResolvedValue(activityResult('Walk'))
    renderWithProviders(<ActivityForm open onClose={() => {}} />)

    fireEvent.click(await screen.findByText('Walk'))
    expect(screen.getByText('Route')).toBeInTheDocument()
    // Bodyweight is never shown unless a pack weight has been entered.
    expect(screen.queryByLabelText(/Bodyweight/)).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/Distance/), { target: { value: '2' } })
    fireEvent.click(screen.getByText('Log activity'))

    await waitFor(() => expect(log).toHaveBeenCalledTimes(1))
    expect(log.mock.calls[0][0]).toMatchObject({ template_key: 'walk', distance: 2 })
    expect(log.mock.calls[0][0].pack_weight).toBeNull()
    expect(log.mock.calls[0][0].bodyweight).toBeNull()
  })

  it('logs a loaded hike with pack + bodyweight and shows the computed load', async () => {
    vi.spyOn(api, 'listActivityTemplates').mockResolvedValue(TEMPLATES)
    const log = vi
      .spyOn(api, 'logActivity')
      .mockResolvedValue(activityResult('Hike', { pack_weight_kg: 20.4, metabolic_cost_kj: 4184 }))
    renderWithProviders(<ActivityForm open onClose={() => {}} />)

    fireEvent.click(await screen.findByText('Hike'))
    expect(await screen.findByText(/Pack weight \(lb/)).toBeInTheDocument()
    expect(screen.getByText(/Distance \(mi\)/)).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/Pack weight/), { target: { value: '45' } })
    fireEvent.change(await screen.findByLabelText(/Bodyweight/), { target: { value: '180' } })

    fireEvent.click(screen.getByText('Log activity'))

    await waitFor(() => expect(log).toHaveBeenCalledTimes(1))
    expect(log.mock.calls[0][0]).toMatchObject({
      template_key: 'hike',
      pack_weight: 45,
      bodyweight: 180,
      terrain: 'trail',
    })
    // Success view surfaces the load (4184 kJ → 1,000 kcal).
    expect(await screen.findByText(/1,000 kcal/)).toBeInTheDocument()
  })

  it('remembers pack + bodyweight for next time, only when a pack was actually logged', async () => {
    vi.spyOn(api, 'listActivityTemplates').mockResolvedValue(TEMPLATES)
    vi.spyOn(api, 'logActivity').mockResolvedValue(activityResult('Hike', { pack_weight_kg: 20.4 }))
    renderWithProviders(<ActivityForm open onClose={() => {}} />)

    fireEvent.click(await screen.findByText('Hike'))
    fireEvent.change(screen.getByLabelText(/Pack weight/), { target: { value: '45' } })
    fireEvent.change(await screen.findByLabelText(/Bodyweight/), { target: { value: '180' } })
    fireEvent.click(screen.getByText('Log activity'))

    await waitFor(() => expect(localStorage.getItem('vires.activity.lastPack')).toBe('45'))
    expect(localStorage.getItem('vires.activity.lastBody')).toBe('180')
  })

  it('trail search fills distance/elevation and logs source route_search', async () => {
    vi.spyOn(api, 'listActivityTemplates').mockResolvedValue(TEMPLATES)
    vi.spyOn(api, 'searchTrails').mockResolvedValue({
      candidates: [
        {
          osm_id: 42,
          name: 'Mailbox Peak Trail',
          distance_m: 8046,
          points: [
            { lat: 47.6, lon: -121.6 },
            { lat: 47.62, lon: -121.6 },
          ],
        },
      ],
      provider_ok: true,
    })
    // 8046 m ⇒ 5 mi.
    vi.spyOn(api, 'measureRoute').mockResolvedValue({
      distance_m: 8046,
      elevation_gain_m: 305,
      point_count: 2,
      duration_s: null,
    })
    const log = vi.spyOn(api, 'logActivity').mockResolvedValue(activityResult('Hike'))
    renderWithProviders(<ActivityForm open onClose={() => {}} />)

    fireEvent.click(await screen.findByText('Hike'))
    fireEvent.click(screen.getByText('Search'))
    fireEvent.change(screen.getByLabelText('trail name'), { target: { value: 'Mailbox Peak' } })
    fireEvent.click(screen.getByText('Find'))
    fireEvent.click(await screen.findByText('Mailbox Peak Trail'))

    await waitFor(() => expect((screen.getByLabelText(/Distance/) as HTMLInputElement).value).toBe('5'))
    fireEvent.click(screen.getByText('Log activity'))
    await waitFor(() => expect(log).toHaveBeenCalled())
    expect(log.mock.calls[0][0].source).toBe('route_search')
  })

  it('draw-on-map measures the traced route and logs source route_draw', async () => {
    vi.spyOn(api, 'listActivityTemplates').mockResolvedValue(TEMPLATES)
    const measure = vi.spyOn(api, 'measureRoute').mockResolvedValue({
      distance_m: 8046,
      elevation_gain_m: 305,
      point_count: 2,
      duration_s: null,
    })
    const log = vi.spyOn(api, 'logActivity').mockResolvedValue(activityResult('Hike'))
    renderWithProviders(<ActivityForm open onClose={() => {}} />)

    fireEvent.click(await screen.findByText('Hike'))
    fireEvent.click(screen.getByText('Draw'))
    // The mocked map stub drops two waypoints when clicked.
    fireEvent.click(screen.getByText('stub-add-2-points'))
    fireEvent.click(screen.getByText(/Measure route \(2 pts\)/))

    await waitFor(() => expect(measure).toHaveBeenCalledTimes(1))
    expect(measure.mock.calls[0][0]).toHaveLength(2)
    await waitFor(() => expect((screen.getByLabelText(/Distance/) as HTMLInputElement).value).toBe('5'))
    fireEvent.click(screen.getByText('Log activity'))
    await waitFor(() => expect(log).toHaveBeenCalled())
    expect(log.mock.calls[0][0].source).toBe('route_draw')
  })

  it('gpx import fills distance + duration and logs source gpx', async () => {
    vi.spyOn(api, 'listActivityTemplates').mockResolvedValue(TEMPLATES)
    vi.spyOn(api, 'importGpx').mockResolvedValue({
      distance_m: 8046,
      elevation_gain_m: 305,
      point_count: 100,
      duration_s: 7200,
    })
    const log = vi.spyOn(api, 'logActivity').mockResolvedValue(activityResult('Hike'))
    renderWithProviders(<ActivityForm open onClose={() => {}} />)

    fireEvent.click(await screen.findByText('Hike'))
    fireEvent.click(screen.getByText('GPX'))
    const file = new File(['<gpx></gpx>'], 'hike.gpx', { type: 'application/gpx+xml' })
    fireEvent.change(screen.getByLabelText('gpx file'), { target: { files: [file] } })

    // 8046 m ⇒ 5 mi distance; 7200 s ⇒ 2h.
    await waitFor(() => expect((screen.getByLabelText(/Distance/) as HTMLInputElement).value).toBe('5'))
    expect((screen.getByLabelText('hours') as HTMLInputElement).value).toBe('2')
    fireEvent.click(screen.getByText('Log activity'))
    await waitFor(() => expect(log).toHaveBeenCalled())
    expect(log.mock.calls[0][0].source).toBe('gpx')
  })
})
