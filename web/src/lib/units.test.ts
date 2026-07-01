import { describe, it, expect } from 'vitest'
import {
  distanceUnit,
  elevationUnit,
  fmtDistance,
  fmtElevation,
  fmtLoad,
  fmtPack,
  kgToDisplay,
  kjToKcal,
  metersToDistance,
  metersToElevation,
  weightToKg,
} from './units'

describe('units — unit labels', () => {
  it('keys distance/elevation off the weight unit', () => {
    expect(distanceUnit('lb')).toBe('mi')
    expect(distanceUnit('kg')).toBe('km')
    expect(elevationUnit('lb')).toBe('ft')
    expect(elevationUnit('kg')).toBe('m')
  })
})

describe('units — display → SI', () => {
  it('converts lb to kg but leaves kg untouched', () => {
    expect(weightToKg(100, 'kg')).toBe(100)
    expect(weightToKg(100, 'lb')).toBeCloseTo(45.359237, 4)
  })
})

describe('units — SI → display (round-trips)', () => {
  it('kg round-trips through display', () => {
    expect(kgToDisplay(weightToKg(45, 'lb'), 'lb')).toBeCloseTo(45, 6)
    expect(kgToDisplay(20, 'kg')).toBe(20)
  })
  it('meters convert to miles/km', () => {
    expect(metersToDistance(1609.344, 'lb')).toBeCloseTo(1, 6)
    expect(metersToDistance(5000, 'kg')).toBeCloseTo(5, 6)
  })
  it('meters convert to feet/meters', () => {
    expect(metersToElevation(304.8, 'lb')).toBeCloseTo(1000, 3)
    expect(metersToElevation(300, 'kg')).toBe(300)
  })
  it('kJ convert to kcal', () => {
    expect(kjToKcal(4.184)).toBeCloseTo(1, 6)
    expect(kjToKcal(0)).toBe(0)
  })
})

describe('units — formatting', () => {
  it('formats pack weight in the account unit', () => {
    expect(fmtPack(weightToKg(45, 'lb'), 'lb')).toBe('45 lb')
    expect(fmtPack(20, 'kg')).toBe('20 kg')
  })
  it('formats distance and elevation, or null when absent', () => {
    expect(fmtDistance(1609.344, 'lb')).toBe('1 mi')
    expect(fmtDistance(null, 'lb')).toBeNull()
    expect(fmtElevation(304.8, 'lb')).toBe('1000 ft')
    expect(fmtElevation(null, 'kg')).toBeNull()
  })
  it('formats load as rounded kcal, or null when uncomputed', () => {
    expect(fmtLoad(4184)).toBe('1,000 kcal')
    expect(fmtLoad(null)).toBeNull()
  })
})
