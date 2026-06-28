import { describe, expect, it } from 'vitest'
import { isoDate, mondayIndex, monthMatrix, sameDay, addMonths } from './calendar'

describe('isoDate', () => {
  it('formats local date as YYYY-MM-DD (no tz shift)', () => {
    expect(isoDate(new Date(2026, 5, 29))).toBe('2026-06-29') // month is 0-based
    expect(isoDate(new Date(2026, 0, 1))).toBe('2026-01-01')
  })
})

describe('mondayIndex', () => {
  it('maps Sunday=6, Monday=0', () => {
    expect(mondayIndex(new Date(2026, 5, 29))).toBe(0) // Mon Jun 29 2026
    expect(mondayIndex(new Date(2026, 5, 28))).toBe(6) // Sun Jun 28 2026
  })
})

describe('monthMatrix', () => {
  it('returns full Monday-aligned weeks covering the month', () => {
    const weeks = monthMatrix(2026, 5) // June 2026
    expect(weeks.every((w) => w.length === 7)).toBe(true)
    // first cell is a Monday
    expect(mondayIndex(weeks[0][0])).toBe(0)
    // June 1 2026 is a Monday -> grid starts exactly on June 1
    expect(isoDate(weeks[0][0])).toBe('2026-06-01')
    // the month's days all appear
    const flat = weeks.flat().map(isoDate)
    expect(flat).toContain('2026-06-30')
  })

  it('pads leading days from the previous month', () => {
    const weeks = monthMatrix(2026, 6) // July 2026 — July 1 is a Wednesday
    expect(isoDate(weeks[0][0])).toBe('2026-06-29') // back to Monday
    expect(isoDate(weeks[0][2])).toBe('2026-07-01')
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
