import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import PlateCalculatorSheet from './PlateCalculatorSheet'

describe('PlateCalculatorSheet', () => {
  it('renders nothing when closed', () => {
    render(<PlateCalculatorSheet open={false} onClose={() => {}} unit="lb" initialWeight={225} />)
    expect(screen.queryByText('Plate calculator')).not.toBeInTheDocument()
  })

  it('seeds the target from initialWeight and shows the per-side breakdown', () => {
    render(<PlateCalculatorSheet open onClose={() => {}} unit="lb" initialWeight={225} />)
    expect(screen.getByDisplayValue('225')).toBeInTheDocument()
    // 225 lb on a 45 lb bar -> 90/side -> two 45s
    const plates = screen.getAllByText('45')
    expect(plates).toHaveLength(2)
  })

  it('recomputes when the target changes, including an unmakeable remainder', () => {
    render(<PlateCalculatorSheet open onClose={() => {}} unit="lb" initialWeight={135} />)
    fireEvent.change(screen.getByLabelText(/Target/), { target: { value: '131' } })
    // 131 lb on a 45 lb bar -> 43/side -> 35 + 5 + 2.5, with 0.5 left over
    expect(screen.getByText("0.5 lb/side can't be made from standard plates.")).toBeInTheDocument()
  })

  it('shows "bar only" when the target is at or below the bar weight', () => {
    render(<PlateCalculatorSheet open onClose={() => {}} unit="kg" initialWeight={20} />)
    expect(screen.getByText('Bar only — no plates needed.')).toBeInTheDocument()
  })
})
