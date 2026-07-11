import { describe, it, expect, vi, afterEach } from 'vitest'
import { api } from './api'
import { getIdentityToken } from './identityToken'

// No shared-identity token by default — requests ride the legacy cookie path
// with bare JSON headers. Individual tests flip the mock to assert the
// Authorization header attaches (vires-ops#60).
vi.mock('./identityToken', () => ({
  getIdentityToken: vi.fn().mockResolvedValue(null),
  clearIdentityToken: vi.fn(),
}))

function mockFetch(opts: { ok?: boolean; status?: number; statusText?: string; json?: unknown } = {}) {
  const f = vi.fn().mockResolvedValue({
    ok: opts.ok ?? true,
    status: opts.status ?? 200,
    statusText: opts.statusText ?? 'OK',
    json: async () => opts.json ?? {},
  } as Response)
  vi.stubGlobal('fetch', f)
  return f
}

afterEach(() => vi.unstubAllGlobals())

describe('req helper', () => {
  it('GETs and returns parsed JSON with JSON headers', async () => {
    const f = mockFetch({ json: [{ id: 1 }] })
    const r = await api.listTemplates()
    expect(r).toEqual([{ id: 1 }])
    expect(f).toHaveBeenCalledWith(
      '/api/templates',
      expect.objectContaining({ headers: { 'Content-Type': 'application/json' } }),
    )
  })

  it('throws "status: detail" on an error with a JSON body', async () => {
    mockFetch({ ok: false, status: 503, json: { detail: 'coach unavailable' } })
    await expect(api.getSettings()).rejects.toThrow('503: coach unavailable')
  })

  it('falls back to statusText when the error body is not JSON', async () => {
    const f = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Server Error',
      json: async () => {
        throw new Error('not json')
      },
    } as unknown as Response)
    vi.stubGlobal('fetch', f)
    await expect(api.getSettings()).rejects.toThrow('500: Server Error')
  })

  it('returns undefined on 204 No Content', async () => {
    mockFetch({ status: 204 })
    await expect(api.deleteTemplate(1)).resolves.toBeUndefined()
  })

  it('URL-encodes the search query and limit', async () => {
    const f = mockFetch({ json: [] })
    await api.searchExercises('over head', 5)
    expect(f).toHaveBeenCalledWith('/api/exercises/search?q=over%20head&limit=5', expect.anything())
  })

  it('POSTs a JSON-serialized body', async () => {
    const f = mockFetch({ json: { id: 1 } })
    await api.startWorkout({ template_id: 7 })
    const [url, init] = f.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/workouts')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ template_id: 7 })
  })

  it('attaches the shared-identity bearer when a token is available', async () => {
    vi.mocked(getIdentityToken).mockResolvedValueOnce('jwt-123')
    const f = mockFetch({ json: [] })
    await api.listTemplates()
    expect(f).toHaveBeenCalledWith(
      '/api/templates',
      expect.objectContaining({
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer jwt-123' },
      }),
    )
  })
})

describe('transcribe (raw blob upload)', () => {
  it('POSTs the blob and returns the text', async () => {
    const f = mockFetch({ json: { text: 'three sets of ten' } })
    const out = await api.transcribe(new Blob(['x'], { type: 'audio/webm' }))
    expect(out).toBe('three sets of ten')
    const [url, init] = f.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/coach/transcribe')
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('audio/webm')
  })

  it('throws on a transcribe error', async () => {
    mockFetch({ ok: false, status: 400, json: { detail: 'no audio' } })
    await expect(api.transcribe(new Blob([]))).rejects.toThrow('400: no audio')
  })
})

describe('every endpoint resolves through req', () => {
  it('exercises the full client surface', async () => {
    const f = mockFetch({ json: {} })
    await Promise.all([
      api.searchExercises('x'),
      api.createExercise({ name: 'x' }),
      api.exerciseHistory(1),
      api.getTemplate(1),
      api.createTemplate({ name: 'x', exercises: [] }),
      api.updateTemplate(1, { name: 'x' }),
      api.deleteTemplate(1),
      api.listWorkouts(),
      api.getWorkout(1),
      api.finishWorkout(1),
      api.deleteWorkout(1),
      api.addWorkoutExercise(1, { exercise_id: 2 }),
      api.removeWorkoutExercise(1, 2),
      api.logSet(1, 2, { reps: 5 }),
      api.updateSet(1, 2, 3, { done: true }),
      api.deleteSet(1, 2, 3),
      api.updateSettings({ weight_unit: 'kg' }),
      api.records('all'),
      api.calendar('2026-06-01', '2026-06-30'),
      api.getPlanned(1),
      api.createPlanned({ scheduled_date: '2026-06-29' }),
      api.updatePlanned(1, { status: 'skipped' }),
      api.deletePlanned(1),
      api.startPlanned(1),
      api.listPrograms(),
      api.deleteProgram(1),
      api.feedUrl(),
      api.rotateFeedUrl(),
      api.coachModifyProgram(1, 'shift it'),
      api.pushPublicKey(),
      api.pushSubscribe({ endpoint: 'e', keys: { p256dh: 'p', auth: 'a' } }),
      api.pushUnsubscribe('e'),
      api.pushSchedule('t1', 60, 'Rest over'),
      api.pushCancel('t1'),
    ])
    expect(f).toHaveBeenCalledTimes(34)
  })
})
