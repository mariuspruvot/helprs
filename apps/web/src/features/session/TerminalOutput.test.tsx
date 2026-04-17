import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, test } from 'vitest'
import TerminalOutput from './TerminalOutput'
import type { TerminalLine } from './containerTypes'

afterEach(() => {
  cleanup()
})

function makeLines(texts: string[]): TerminalLine[] {
  return texts.map((text, i) => ({
    id: i + 1,
    text,
    timestamp: Date.now() + i,
  }))
}

describe('TerminalOutput', () => {
  test('renders with no lines and not running', () => {
    render(<TerminalOutput lines={[]} isRunning={false} />)

    expect(screen.getByTestId('terminal-output')).toBeTruthy()
    expect(screen.getByText('No output yet.')).toBeTruthy()
  })

  test('renders lines of text', () => {
    const lines = makeLines(['Hello world', 'Second line', 'Third line'])
    render(<TerminalOutput lines={lines} isRunning={false} />)

    expect(screen.getByText('Hello world')).toBeTruthy()
    expect(screen.getByText('Second line')).toBeTruthy()
    expect(screen.getByText('Third line')).toBeTruthy()
  })

  test('shows running indicator when isRunning is true', () => {
    render(<TerminalOutput lines={makeLines(['test'])} isRunning={true} />)

    expect(screen.getByTestId('terminal-running-indicator')).toBeTruthy()
    expect(screen.getByText('running')).toBeTruthy()
  })

  test('hides running indicator when not running', () => {
    render(<TerminalOutput lines={makeLines(['test'])} isRunning={false} />)

    expect(screen.queryByTestId('terminal-running-indicator')).toBeNull()
  })

  test('shows cursor when running and lines exist', () => {
    render(<TerminalOutput lines={makeLines(['test'])} isRunning={true} />)

    expect(screen.getByTestId('terminal-cursor')).toBeTruthy()
  })

  test('hides cursor when not running', () => {
    render(<TerminalOutput lines={makeLines(['test'])} isRunning={false} />)

    expect(screen.queryByTestId('terminal-cursor')).toBeNull()
  })

  test('has accessible log role', () => {
    render(<TerminalOutput lines={[]} isRunning={false} />)

    expect(screen.getByRole('log')).toBeTruthy()
  })

  test('renders terminal header with session label', () => {
    render(<TerminalOutput lines={[]} isRunning={false} />)

    expect(screen.getByText('helPRs session')).toBeTruthy()
  })
})
