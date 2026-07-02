import { describe, expect, it } from 'vitest'
import { getHealthSource, normalizeWorkout, workoutToRouteStats } from './health'

describe('normalizeWorkout', () => {
  it('normalizes a well-formed native record', () => {
    const w = normalizeWorkout({
      id: 'abc',
      type: 'hike',
      startedAt: '2026-07-01T14:00:00Z',
      distanceM: 8200,
      elevationGainM: 640,
      durationS: 7200,
    })
    expect(w).toEqual({
      id: 'abc',
      type: 'hike',
      startedAt: '2026-07-01T14:00:00Z',
      distanceM: 8200,
      elevationGainM: 640,
      durationS: 7200,
    })
  })

  it('defaults an unknown type to walk', () => {
    expect(normalizeWorkout({ id: 'x', type: 'running', distanceM: 100, durationS: 60 })?.type).toBe(
      'walk',
    )
  })

  it('treats missing / negative / non-finite elevation as null', () => {
    expect(normalizeWorkout({ id: 'a', distanceM: 100, durationS: 60 })?.elevationGainM).toBeNull()
    expect(
      normalizeWorkout({ id: 'b', distanceM: 100, durationS: 60, elevationGainM: -5 })
        ?.elevationGainM,
    ).toBeNull()
  })

  it('rejects records with unusable distance or duration', () => {
    expect(normalizeWorkout({ id: 'a', distanceM: NaN, durationS: 60 })).toBeNull()
    expect(normalizeWorkout({ id: 'a', distanceM: -1, durationS: 60 })).toBeNull()
    expect(normalizeWorkout({ id: 'a', distanceM: 100, durationS: 0 })).toBeNull()
    expect(normalizeWorkout({ id: 'a', distanceM: 100 })).toBeNull()
  })

  it('synthesizes a stable id when the record omits one', () => {
    const w = normalizeWorkout({ startedAt: '2026-07-01T00:00:00Z', distanceM: 100, durationS: 60 })
    expect(w?.id).toBe('health-2026-07-01T00:00:00Z')
  })
})

describe('workoutToRouteStats', () => {
  it('projects a workout onto SI RouteStats with no track points', () => {
    expect(
      workoutToRouteStats({
        id: 'a',
        type: 'walk',
        startedAt: '2026-07-01T00:00:00Z',
        distanceM: 5000,
        elevationGainM: 120,
        durationS: 3600,
      }),
    ).toEqual({ distance_m: 5000, elevation_gain_m: 120, point_count: 0, duration_s: 3600 })
  })
})

describe('getHealthSource (web)', () => {
  it('is unavailable off a native shell, so the Health UI stays hidden', async () => {
    const source = getHealthSource()
    expect(await source.isAvailable()).toBe(false)
    expect(await source.requestPermission()).toBe(false)
    expect(await source.recentWorkouts()).toEqual([])
  })
})
