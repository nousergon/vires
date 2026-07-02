import { describe, it, expect } from 'vitest'
import { calculatePlates, DEFAULT_BAR_WEIGHT } from './plates'

describe('calculatePlates', () => {
  it('returns bar-only for a target at or below the bar weight', () => {
    expect(calculatePlates(45, 45, 'lb').perSide).toEqual([])
    expect(calculatePlates(30, 45, 'lb').perSide).toEqual([])
  })

  it('greedily fills one side with the largest plates first (lb)', () => {
    // 225 lb = 45 bar + 90/side -> 45 + 45
    expect(calculatePlates(225, 45, 'lb').perSide).toEqual([45, 45])
    // 135 lb = 45 bar + 45/side -> 45
    expect(calculatePlates(135, 45, 'lb').perSide).toEqual([45])
    // 185 lb = 45 bar + 70/side -> 45 + 25
    expect(calculatePlates(185, 45, 'lb').perSide).toEqual([45, 25])
  })

  it('greedily fills one side with the largest plates first (kg)', () => {
    // 100 kg = 20 bar + 40/side -> 25 + 15
    expect(calculatePlates(100, 20, 'kg').perSide).toEqual([25, 15])
  })

  it('reports a remainder when the target cannot be made exactly', () => {
    const { perSide, remainder } = calculatePlates(46, 45, 'lb')
    expect(perSide).toEqual([])
    expect(remainder).toBeCloseTo(0.5)
  })

  it('defaults to the standard Olympic bar weight', () => {
    expect(DEFAULT_BAR_WEIGHT.lb).toBe(45)
    expect(DEFAULT_BAR_WEIGHT.kg).toBe(20)
  })
})
