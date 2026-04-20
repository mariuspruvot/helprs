import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, test } from 'vitest'
import LandingPage from './LandingPage'

afterEach(() => cleanup())

describe('LandingPage', () => {
  test('renders hero heading', () => {
    render(<LandingPage />)
    const heading = screen.getByRole('heading', { level: 1 })
    expect(heading.textContent).toMatch(/AI skills for every/)
    expect(heading.textContent).toMatch(/pull request/)
  })

  test('renders hero subtitle with Claude Code link', () => {
    render(<LandingPage />)
    const claudeLink = screen.getByRole('link', { name: /Claude Code/ })
    expect(claudeLink.getAttribute('href')).toContain('anthropic.com')
  })

  test('renders View on GitHub CTA links', () => {
    render(<LandingPage />)
    const links = screen.getAllByRole('link', { name: /view on github/i })
    expect(links.length).toBe(2)
    for (const link of links) {
      expect(link.getAttribute('href')).toContain('github.com/mariuspruvot/helprs')
    }
  })

  test('renders Self-hosting guide CTA links', () => {
    render(<LandingPage />)
    const links = screen.getAllByRole('link', { name: /self-hosting guide/i })
    expect(links.length).toBe(2)
    for (const link of links) {
      expect(link.getAttribute('href')).toContain('docs/self-hosting.md')
    }
  })

  test('renders "How it works" section with 3 steps', () => {
    render(<LandingPage />)
    expect(screen.getByText('From webhook to results')).toBeTruthy()
    expect(screen.getByText('Webhook received')).toBeTruthy()
    expect(screen.getByText('Container runs skill')).toBeTruthy()
    expect(screen.getByText('Live results, then cleanup')).toBeTruthy()
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
    expect(text).toContain('localhost:5173')
  })

  test('renders Install GitHub App link in get started section', () => {
    render(<LandingPage />)
    const link = screen.getByRole('link', { name: /install the github app/i })
    expect(link.getAttribute('href')).toContain('github.com/apps/')
    expect(link.getAttribute('href')).toContain('/installations/new')
  })

  test('renders sign-in links', () => {
    render(<LandingPage />)
    const signInLinks = screen.getAllByRole('link', { name: /sign in/i })
    expect(signInLinks.length).toBeGreaterThanOrEqual(2)
    for (const link of signInLinks) {
      expect(link.getAttribute('href')).toContain('/api/v1/auth/github')
    }
  })

  test('renders GitHub link in header', () => {
    render(<LandingPage />)
    const ghLinks = screen.getAllByRole('link', { name: /^GitHub$/ })
    expect(ghLinks.length).toBeGreaterThanOrEqual(2)
    expect(ghLinks[0].getAttribute('href')).toContain('github.com/mariuspruvot/helprs')
  })

  test('renders footer with GitHub link', () => {
    render(<LandingPage />)
    const ghLinks = screen.getAllByRole('link', { name: /^GitHub$/ })
    const footerLink = ghLinks[ghLinks.length - 1]
    expect(footerLink.getAttribute('href')).toContain('github.com/mariuspruvot/helprs')
    expect(footerLink.getAttribute('target')).toBe('_blank')
  })

  test('hero heading uses responsive text size classes', () => {
    render(<LandingPage />)
    const heading = screen.getByRole('heading', { level: 1 })
    expect(heading.className).toContain('text-[32px]')
    expect(heading.className).toContain('md:text-[40px]')
    expect(heading.className).toContain('lg:text-[52px]')
  })

  test('mentions open-source and self-hosted nature', () => {
    const { container } = render(<LandingPage />)
    const text = container.textContent?.toLowerCase() ?? ''
    expect(text).toContain('open-source')
    expect(text).toContain('self-hosted')
    expect(text).toContain('mit licensed')
  })
})
