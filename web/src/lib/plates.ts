import type { WeightUnit } from './api'

/** Standard plate sizes available on a home/commercial rack, heaviest first. */
export const PLATE_SIZES: Record<WeightUnit, number[]> = {
  lb: [45, 35, 25, 10, 5, 2.5],
  kg: [25, 20, 15, 10, 5, 2.5, 1.25],
}

/** Standard Olympic barbell weight. */
export const DEFAULT_BAR_WEIGHT: Record<WeightUnit, number> = { lb: 45, kg: 20 }

export type PlateBreakdown = {
  /** Plates for ONE side of the bar, heaviest first (each loaded on both sides). */
  perSide: number[]
  /** Portion of the target that can't be made from the available plate sizes. */
  remainder: number
}

/**
 * Greedily fill one side of the bar with the largest plates that fit. Barbell
 * math is symmetric (same plates on both sides), so this works off half the
 * weight above the bar.
 */
export function calculatePlates(
  targetWeight: number,
  barWeight: number,
  unit: WeightUnit,
): PlateBreakdown {
  let perSideRemaining = Math.max(0, targetWeight - barWeight) / 2
  const perSide: number[] = []
  for (const plate of PLATE_SIZES[unit]) {
    // Round to avoid float drift (e.g. 0.1 + 0.2) accumulating across plates.
    while (perSideRemaining + 1e-9 >= plate) {
      perSide.push(plate)
      perSideRemaining = Math.round((perSideRemaining - plate) * 100) / 100
    }
  }
  return { perSide, remainder: perSideRemaining }
}
