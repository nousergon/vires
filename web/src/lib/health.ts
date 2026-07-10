// Terms-clean automatic ruck capture (vires-ops#37).
//
// Reads completed hike/walk workouts from the *phone's own* health store
// (Apple HealthKit / Android Health Connect) via a Capacitor native plugin.
// Because it is the user's own on-device data there is no third-party API,
// no AI-use prohibition (unblocks coach load-accounting), and no display
// restriction — the reason this replaces the Strava path (vires-ops#36).
//
// This module is the TypeScript SEAM only: the interface, the SI normalizer,
// and the platform-selecting factory. The native plugin implementations live
// in the generated `ios/` / `android/` Capacitor projects (a HealthKit query
// on iOS, a Health Connect read on Android) and require Xcode / the Android
// SDK + a device to build — they are intentionally out of this module.
//
// Everything the health store gives us is already SI (HealthKit distance in
// metres, elevation-ascended in metres, duration in seconds; Health Connect
// likewise), so it drops straight into the app's SI-canonical route pipeline
// (`RouteStats`) with no conversion — Tier 0's SI-canonical decision paying off.

import { Capacitor, registerPlugin } from '@capacitor/core'
import type { RouteStats } from './api'

// A completed workout read from the device health store, normalized to SI.
export interface HealthWorkout {
  // Stable per-workout id (HealthKit UUID / Health Connect record id) — used
  // as the React key and to dedupe re-imports.
  id: string
  type: 'walk' | 'hike'
  // ISO-8601 start instant, for display + backdating the logged session.
  startedAt: string
  distanceM: number
  // Not every workout records elevation; null when the store has none.
  elevationGainM: number | null
  durationS: number
}

// Pluggable source of completed workouts. `isAvailable` gates the whole UI:
// on the web PWA (no native shell) it resolves false and the Health option
// never renders, so the standalone PWA is byte-unaffected.
export interface HealthSource {
  isAvailable(): Promise<boolean>
  // Idempotent; resolves true once read permission for workouts is granted.
  requestPermission(): Promise<boolean>
  // Completed hike/walk workouts within the last `sinceDays`, newest first.
  recentWorkouts(sinceDays?: number): Promise<HealthWorkout[]>
}

// ---- native bridge -------------------------------------------------------- //

// Shape returned by the native plugin. Mirrors HealthWorkout but is treated as
// untrusted (values may be missing / non-finite) and normalized below.
interface NativeWorkout {
  id?: string
  type?: string
  startedAt?: string
  distanceM?: number
  elevationGainM?: number | null
  durationS?: number
}

interface HealthPlugin {
  requestPermission(): Promise<{ granted: boolean }>
  recentWorkouts(options: { sinceDays: number }): Promise<{ workouts: NativeWorkout[] }>
}

// Registered lazily-typed against the native impl; on web this proxy exists but
// its methods reject (isAvailable() short-circuits before we ever call them).
const HealthNative = registerPlugin<HealthPlugin>('Health')

const DEFAULT_SINCE_DAYS = 30

// Coerce one untrusted native record into a HealthWorkout, or null if it is
// unusable (no id, or non-finite/negative distance/duration). Pure + exported
// so the normalization contract is unit-tested without a device.
export function normalizeWorkout(raw: NativeWorkout, index = 0): HealthWorkout | null {
  const distanceM = Number(raw.distanceM)
  const durationS = Number(raw.durationS)
  if (!Number.isFinite(distanceM) || distanceM < 0) return null
  if (!Number.isFinite(durationS) || durationS <= 0) return null

  const elev = raw.elevationGainM
  const elevationGainM =
    elev == null || !Number.isFinite(Number(elev)) || Number(elev) < 0 ? null : Number(elev)

  return {
    id: raw.id && raw.id.length > 0 ? raw.id : `health-${raw.startedAt ?? index}`,
    type: raw.type === 'hike' ? 'hike' : 'walk',
    startedAt: raw.startedAt ?? '',
    distanceM,
    elevationGainM,
    durationS,
  }
}

// A health workout, projected onto the same SI RouteStats the trail/draw/GPX
// derivations produce — so it reuses `RouteCapture.applyStats` verbatim.
export function workoutToRouteStats(w: HealthWorkout): RouteStats {
  return {
    distance_m: w.distanceM,
    elevation_gain_m: w.elevationGainM,
    // The health store gives aggregate totals, not a traced path.
    point_count: 0,
    duration_s: w.durationS,
  }
}

class CapacitorHealthSource implements HealthSource {
  async isAvailable(): Promise<boolean> {
    // Native shell only; the plugin has no web implementation.
    return Capacitor.isNativePlatform() && Capacitor.isPluginAvailable('Health')
  }

  async requestPermission(): Promise<boolean> {
    const { granted } = await HealthNative.requestPermission()
    return granted
  }

  async recentWorkouts(sinceDays = DEFAULT_SINCE_DAYS): Promise<HealthWorkout[]> {
    const { workouts } = await HealthNative.recentWorkouts({ sinceDays })
    return workouts
      .map((w, i) => normalizeWorkout(w, i))
      .filter((w): w is HealthWorkout => w !== null)
      .sort((a, b) => b.startedAt.localeCompare(a.startedAt))
  }
}

// Web / non-native fallback: never available, so the Health UI stays hidden and
// the standalone PWA behaves exactly as before.
class UnavailableHealthSource implements HealthSource {
  async isAvailable(): Promise<boolean> {
    return false
  }
  async requestPermission(): Promise<boolean> {
    return false
  }
  async recentWorkouts(): Promise<HealthWorkout[]> {
    return []
  }
}

let cached: HealthSource | null = null

// Single entry point. Native source under a Capacitor shell, otherwise the
// unavailable stub. Memoized so RouteCapture can call it freely.
export function getHealthSource(): HealthSource {
  if (cached) return cached
  cached = Capacitor.isNativePlatform() ? new CapacitorHealthSource() : new UnavailableHealthSource()
  return cached
}
