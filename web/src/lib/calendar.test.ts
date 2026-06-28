import { describe, expect, it } from 'vitest'
import { isoDate, monthMatrix, sameDay, addMonths } from './calendar'

describe('isoDate', () => {
  it('formats local date as YYYY-MM-DD (no tz shift)', () => {
    expect(isoDate(new Date(2026, 5, 29))).toBe('2026-06-29') // month is 0-based
    expect(isoDate(new Date(2026, 0, 1))).toBe('2026-01-01')
  })
})

describe('monthMatrix (Sunday-first)', () => {
  it('returns full Sunday-aligned weeks covering the month', () => {
    const weeks = monthMatrix(2026, 5) // June 2026 — June 1 is a Monday
    expect(weeks.every((w) => w.length === 7)).toBe(true)
    // every row starts on a Sunday
    expect(weeks.every((w) => w[0].getDay() === 0)).toBe(true)
    // grid pads back one day to Sunday May 31
    expect(isoDate(weeks[0][0])).toBe('2026-05-31')
    expect(isoDate(weeks[0][1])).toBe('2026-06-01') // Monday in the 2nd column
    // the month's days all appear
    expect(weeks.flat().map(isoDate)).toContain('2026-06-30')
  })

  it('pads leading days from the previous month', () => {
    const weeks = monthMatrix(2026, 6) // July 2026 — July 1 is a Wednesday
    expect(isoDate(weeks[0][0])).toBe('2026-06-28') // back to Sunday
    expect(weeks[0][0].getDay()).toBe(0)
    expect(isoDate(weeks[0][3])).toBe('2026-07-01') // Wednesday = 4th column
  })
})

describe('sameDay / addMonths', () => {
  it('sameDay ignores time', () => {
    expect(sameDay(new Date(2026, 5, 1, 9), new Date(2026, 5, 1, 23))).toBe(true)
    expect(sameDay(new Date(2026, 5, 1), new Date(2026, 5, 2))).toBe(false)
  })
  it('addMonths returns first of the shifted month', () => {
    expect(isoDate(addMonths(new Date(2026, 5, 15), 1))).toBe('2026-07-01')
    expect(isoDate(addMonths(new Date(2026, 0, 10), -1))).toBe('2025-12-01')
  })
})
