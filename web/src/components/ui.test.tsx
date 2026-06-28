import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { Button, Card, EmptyState, PageTitle, Sheet, Spinner } from './ui'

describe('Button', () => {
  it('renders children and fires onClick', () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Go</Button>)
    fireEvent.click(screen.getByRole('button', { name: 'Go' }))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('does not fire when disabled', () => {
    const onClick = vi.fn()
    render(
      <Button disabled onClick={onClick}>
        Nope
      </Button>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Nope' }))
    expect(onClick).not.toHaveBeenCalled()
  })

  it('applies the variant class', () => {
    render(<Button variant="danger">Del</Button>)
    expect(screen.getByRole('button', { name: 'Del' }).className).toContain('bg-red-600')
  })
})

describe('Card / EmptyState / PageTitle / Spinner', () => {
  it('Card renders children', () => {
    render(<Card>content</Card>)
    expect(screen.getByText('content')).toBeInTheDocument()
  })

  it('EmptyState shows title and hint', () => {
    render(<EmptyState title="Nothing here" hint="add one" />)
    expect(screen.getByText('Nothing here')).toBeInTheDocument()
    expect(screen.getByText('add one')).toBeInTheDocument()
  })

  it('PageTitle shows title and the right slot', () => {
    render(<PageTitle right={<span>R</span>}>Plan</PageTitle>)
    expect(screen.getByText('Plan')).toBeInTheDocument()
    expect(screen.getByText('R')).toBeInTheDocument()
  })

  it('Spinner renders an animated element', () => {
    const { container } = render(<Spinner />)
    expect(container.querySelector('.animate-spin')).toBeTruthy()
  })
})

describe('Sheet', () => {
  it('renders nothing when closed', () => {
    render(
      <Sheet open={false} onClose={() => {}} title="S">
        body
      </Sheet>,
    )
    expect(screen.queryByText('body')).not.toBeInTheDocument()
  })

  it('shows content when open and closes via the ✕ button', () => {
    const onClose = vi.fn()
    render(
      <Sheet open onClose={onClose} title="My Sheet">
        sheet body
      </Sheet>,
    )
    expect(screen.getByText('My Sheet')).toBeInTheDocument()
    expect(screen.getByText('sheet body')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Close'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
