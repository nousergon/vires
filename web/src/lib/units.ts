// Unit conversion + display formatting for activity route + pack-weight data.
//
// The API stores and returns canonical SI (kg / m / s); the account's
// `weight_unit` drives how we render it. To avoid adding a separate
// distance-unit setting, distance/elevation follow the weight unit: 'lb'
// accounts see miles/feet, 'kg' accounts see km/meters. This mirrors the
// server-side boundary conversion in api/routers/workouts.py.

import type { WeightUnit } from './api'

const LB_TO_KG = 0.45359237
const MILE_TO_M = 1609.344
const KM_TO_M = 1000
const FOOT_TO_M = 0.3048
const KJ_TO_KCAL = 1 / 4.184

export function distanceUnit(w: WeightUnit): 'mi' | 'km' {
  return w === 'kg' ? 'km' : 'mi'
}

export function elevationUnit(w: WeightUnit): 'ft' | 'm' {
  return w === 'kg' ? 'm' : 'ft'
}

// ---- display value → SI (for building a log payload) ---------------------- //
export function weightToKg(v: number, w: WeightUnit): number {
  return w === 'kg' ? v : v * LB_TO_KG
}

// ---- SI → display value (for rendering) ----------------------------------- //
export function kgToDisplay(kg: number, w: WeightUnit): number {
  return w === 'kg' ? kg : kg / LB_TO_KG
}

export function metersToDistance(m: number, w: WeightUnit): number {
  return m / (w === 'kg' ? KM_TO_M : MILE_TO_M)
}

export function metersToElevation(m: number, w: WeightUnit): number {
  return m / (w === 'kg' ? 1 : FOOT_TO_M)
}

export function kjToKcal(kj: number): number {
  return kj * KJ_TO_KCAL
}

// ---- formatting ----------------------------------------------------------- //
const round = (n: number, dp: number) => {
  const f = 10 ** dp
  return Math.round(n * f) / f
}

export function fmtPack(kg: number | null, w: WeightUnit): string | null {
  if (kg == null) return null
  return `${round(kgToDisplay(kg, w), 1)} ${w}`
}

export function fmtDistance(m: number | null, w: WeightUnit): string | null {
  if (m == null) return null
  return `${round(metersToDistance(m, w), 2)} ${distanceUnit(w)}`
}

export function fmtElevation(m: number | null, w: WeightUnit): string | null {
  if (m == null) return null
  return `${Math.round(metersToElevation(m, w))} ${elevationUnit(w)}`
}

// Metabolic cost shown in kcal — the intuitive "energy burned" number, and the
// one that actually moves with pack weight (the whole point of the feature).
export function fmtLoad(kj: number | null): string | null {
  if (kj == null) return null
  return `${Math.round(kjToKcal(kj)).toLocaleString()} kcal`
}
