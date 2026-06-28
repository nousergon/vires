// Pure date math for the month calendar — no deps (the app deliberately avoids
// a heavy date library). Weeks start on Sunday (US calendar standard).

/** Local-time YYYY-MM-DD (NOT toISOString, which would shift by timezone). */
export function isoDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

export function addMonths(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth() + n, 1)
}

export function startOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1)
}

export function sameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  )
}

/**
 * The calendar grid for a month as full Sunday→Saturday weeks. Leading/trailing
 * cells spill into the adjacent months so every row has 7 days.
 */
export function monthMatrix(year: number, month: number): Date[][] {
  const first = new Date(year, month, 1)
  const lead = first.getDay() // 0=Sunday … 6=Saturday
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const cells = Math.ceil((lead + daysInMonth) / 7) * 7
  const gridStart = new Date(year, month, 1 - lead)
  const weeks: Date[][] = []
  for (let i = 0; i < cells; i++) {
    if (i % 7 === 0) weeks.push([])
    weeks[weeks.length - 1].push(
      new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + i),
    )
  }
  return weeks
}

export const WEEKDAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
export const MONTH_LABELS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]
