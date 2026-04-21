import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, test } from 'vitest'
import LandingPage from './LandingPage'

afterEach(() => cleanup())

describe('LandingPage', () => {
  test('renders hero heading', () => {
    render(<LandingPage />)
    const heading = screen.getByRole('heading', { level: 1 })
    expect(heading.textContent).toContain('interrogated')
  })

  test('renders View on GitHub CTA links', () => {
    render(<LandingPage />)
    const buttons = screen.getAllByText(/view on github/i)
    expect(buttons.length).toBe(2)
  })

  test('renders Self-hosting guide CTA links', () => {
    render(<LandingPage />)
    const buttons = screen.getAllByText(/self-hosting guide/i)
    expect(buttons.length).toBe(2)
  })

  test('renders "How it works" section with 3 steps', () => {
    render(<LandingPage />)
    expect(screen.getByText('From webhook to results')).toBeTruthy()
    expect(screen.getByText('Webhook received')).toBeTruthy()
    expect(screen.getByText('Container runs skill')).toBeTruthy()
    expect(screen.getByText('Score and learn')).toBeTruthy()
  })

  test('renders terminal-like visuals for each step', () => {
    const { container } = render(<LandingPage />)
    const text = container.textContent ?? ''
    expect(text).toContain('PR #42')
    expect(text).toContain('claude-runner')
    expect(text).toContain('container destroyed')
  })

  test('renders self-hosted features section', () => {
    render(<LandingPage />)
    expect(screen.getByText('Your infrastructure, your data')).toBeTruthy()
    expect(screen.getByText('Bring Your Own Key')).toBeTruthy()
    expect(screen.getByText('Ephemeral containers')).toBeTruthy()
    expect(screen.getByText('Open source')).toBeTruthy()
  })

  test('renders get started section with docker compose terminal', () => {
    const { container } = render(<LandingPage />)
    const text = container.textContent ?? ''
    expect(screen.getByText('Deploy in minutes')).toBeTruthy()
    expect(text).toContain('docker compose up --build')
    expect(text).toContain('localhost:8000')
  })

  test('renders Install GitHub App link', () => {
    render(<LandingPage />)
    const link = screen.getByRole('link', { name: /install the github app/i })
    expect(link.getAttribute('href')).toContain('github.com/apps/')
  })

  test('renders sign-in link', () => {
    render(<LandingPage />)
    const links = screen.getAllByRole('link', { name: /sign in/i })
    expect(links.length).toBeGreaterThanOrEqual(2)
  })

  test('renders example session card', () => {
    const { container } = render(<LandingPage />)
    const text = container.textContent ?? ''
    expect(text).toContain('Retry-After header')
  })

  test('renders stats strip', () => {
    render(<LandingPage />)
    expect(screen.getByText('Interactive')).toBeTruthy()
    expect(screen.getByText('MIT')).toBeTruthy()
  })

  test('renders footer', () => {
    render(<LandingPage />)
    const ghLinks = screen.getAllByRole('link', { name: /^GitHub$/ })
    expect(ghLinks.length).toBeGreaterThanOrEqual(2)
  })

  test('mentions open-source and self-hosted nature', () => {
    const { container } = render(<LandingPage />)
    const text = container.textContent?.toLowerCase() ?? ''
    expect(text).toContain('open-source')
    expect(text).toContain('self-hosted')
    expect(text).toContain('mit licensed')
  })
})
