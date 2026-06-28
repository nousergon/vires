import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import { renderWithProviders } from '../test/utils'
import PlanPage from './PlanPage'
import { api } from '../lib/api'

beforeEach(() => vi.restoreAllMocks())

function mockEmpty() {
  vi.spyOn(api, 'calendar').mockResolvedValue([])
  vi.spyOn(api, 'listPrograms').mockResolvedValue([])
  vi.spyOn(api, 'listTemplates').mockResolvedValue([])
}

describe('PlanPage', () => {
  it('renders the month grid with Sunday-first weekday headers', async () => {
    mockEmpty()
    renderWithProviders(<PlanPage />)
    expect(await screen.findByText('Plan')).toBeInTheDocument()
    // Sunday-first header row (grid renders after the calendar query resolves)
    const sun = await screen.findByText('Sun')
    expect(sun.parentElement?.textContent).toBe('SunMonTueWedThuFriSat')
    // the coach entry point is present
    expect(screen.getByText('✨ Coach')).toBeInTheDocument()
  })

  it('opens the coach sheet when ✨ Coach is tapped', async () => {
    mockEmpty()
    renderWithProviders(<PlanPage />)
    fireEvent.click(await screen.findByText('✨ Coach'))
    // CoachSheet (create mode) shows its prompt
    expect(await screen.findByText(/lays workouts onto your calendar/i)).toBeInTheDocument()
  })

  it('lists active programs from the API', async () => {
    vi.spyOn(api, 'calendar').mockResolvedValue([])
    vi.spyOn(api, 'listTemplates').mockResolvedValue([])
    vi.spyOn(api, 'listPrograms').mockResolvedValue([
      {
        id: 1,
        name: '8-Week Block',
        goal_text: null,
        start_date: '2026-06-29',
        end_date: '2026-08-20',
        status: 'active',
        planned_count: 16,
        completed_count: 2,
      },
    ])
    renderWithProviders(<PlanPage />)
    expect(await screen.findByText('8-Week Block')).toBeInTheDocument()
    expect(screen.getByText(/2\/16 done/)).toBeInTheDocument()
    expect(screen.getByText('Modify')).toBeInTheDocument()
  })
})
