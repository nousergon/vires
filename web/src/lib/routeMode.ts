import type { RouteSource } from './api'

// The flexible route-input modes shared by RouteCapture + its callers.
// All populate the same editable distance/elevation/duration fields and
// report which mode produced them via `source`, tagged onto the eventual
// log payload. Shared by every route-capable activity template
// (walk/run/hike) — not specific to any one of them.
//
// `health` is native-only (Capacitor HealthKit / Health Connect); RouteCapture
// hides its tab unless a health source `isAvailable()`, so the web PWA still
// only sees the four flexible modes.
export type RouteMode = 'manual' | 'trail' | 'draw' | 'gpx' | 'health'

const MODES: { key: RouteMode; label: string; source: RouteSource }[] = [
  { key: 'manual', label: 'Manual', source: 'manual' },
  { key: 'trail', label: 'Search', source: 'route_search' },
  { key: 'draw', label: 'Draw', source: 'route_draw' },
  { key: 'gpx', label: 'GPX', source: 'gpx' },
  { key: 'health', label: 'Health', source: 'health' },
]

export const ROUTE_MODES = MODES

export function modeSource(mode: RouteMode): RouteSource {
  return MODES.find((m) => m.key === mode)!.source
}
