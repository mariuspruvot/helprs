import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, test } from 'vitest'
import { Button, Card, Chip, Dot, GrainOverlay, Overline, StatCard, TerminalBlock } from './index'

afterEach(() => cleanup())

describe('Chip', () => {
  test('renders children with default variant', () => {
    render(<Chip>status</Chip>)
    expect(screen.getByText('status')).toBeTruthy()
  })

  test('applies variant classes', () => {
    const { container } = render(<Chip variant="accent">active</Chip>)
    const chip = container.querySelector('span')
    expect(chip?.className).toContain('text-accent')
  })

  test('accepts custom className', () => {
    const { container } = render(<Chip className="ml-2">tag</Chip>)
    const chip = container.querySelector('span')
    expect(chip?.className).toContain('ml-2')
  })
})

describe('Card', () => {
  test('renders children', () => {
    render(<Card>content</Card>)
    expect(screen.getByText('content')).toBeTruthy()
  })

  test('applies hover classes when hover prop is true', () => {
    const { container } = render(<Card hover>hoverable</Card>)
    const card = container.firstElementChild as HTMLElement
    expect(card.className).toContain('hover:bg-card-hi')
  })

  test('does not apply hover classes by default', () => {
    const { container } = render(<Card>static</Card>)
    const card = container.firstElementChild as HTMLElement
    expect(card.className).not.toContain('hover:bg-card-hi')
  })
})

describe('Button', () => {
  test('renders with primary variant by default', () => {
    const { container } = render(<Button>Click</Button>)
    const btn = container.querySelector('button')
    expect(btn?.className).toContain('bg-accent')
  })

  test('renders secondary variant', () => {
    const { container } = render(<Button variant="secondary">Cancel</Button>)
    const btn = container.querySelector('button')
    expect(btn?.className).toContain('border-rule-str')
  })

  test('renders danger variant', () => {
    const { container } = render(<Button variant="danger">Delete</Button>)
    const btn = container.querySelector('button')
    expect(btn?.className).toContain('text-danger')
  })

  test('passes through button attributes', () => {
    render(<Button disabled>Disabled</Button>)
    const btn = screen.getByRole('button')
    expect(btn).toHaveProperty('disabled', true)
  })
})

describe('StatCard', () => {
  test('renders label and value', () => {
    render(<StatCard label="Sessions" value={42} />)
    expect(screen.getByText('Sessions')).toBeTruthy()
    expect(screen.getByText('42')).toBeTruthy()
  })

  test('renders sub text when provided', () => {
    render(<StatCard label="Score" value="8.5" sub="avg this week" />)
    expect(screen.getByText('avg this week')).toBeTruthy()
  })

  test('applies color to value', () => {
    const { container } = render(<StatCard label="OK" value={10} color="ok" />)
    const value = container.querySelector('.text-ok')
    expect(value?.textContent).toBe('10')
  })
})

describe('TerminalBlock', () => {
  test('renders children as code content', () => {
    render(<TerminalBlock>$ echo hello</TerminalBlock>)
    expect(screen.getByText('$ echo hello')).toBeTruthy()
  })

  test('renders title when provided', () => {
    render(<TerminalBlock title="entrypoint.sh">code</TerminalBlock>)
    expect(screen.getByText('entrypoint.sh')).toBeTruthy()
  })

  test('renders macOS traffic lights', () => {
    const { container } = render(<TerminalBlock>code</TerminalBlock>)
    const dots = container.querySelectorAll('.rounded-full')
    expect(dots.length).toBe(3)
  })
})

describe('GrainOverlay', () => {
  test('renders with pointer-events-none', () => {
    const { container } = render(<GrainOverlay />)
    const el = container.firstElementChild as HTMLElement
    expect(el.className).toContain('pointer-events-none')
  })
})

describe('Overline', () => {
  test('renders children with uppercase styling', () => {
    const { container } = render(<Overline>section label</Overline>)
    const el = container.firstElementChild as HTMLElement
    expect(el.textContent).toBe('section label')
    expect(el.className).toContain('uppercase')
  })
})

describe('Dot', () => {
  test('renders with default ok color', () => {
    const { container } = render(<Dot />)
    const dot = container.querySelector('span')
    expect(dot?.className).toContain('bg-ok')
  })

  test('applies pulse animation when pulse prop is true', () => {
    const { container } = render(<Dot pulse />)
    const dot = container.querySelector('span')
    expect(dot?.className).toContain('animate-')
  })

  test('renders with specified color', () => {
    const { container } = render(<Dot color="danger" />)
    const dot = container.querySelector('span')
    expect(dot?.className).toContain('bg-danger')
  })
})
