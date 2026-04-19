import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, test } from 'vitest'
import LandingPage from './LandingPage'

afterEach(() => cleanup())

describe('LandingPage', () => {
  test('renders hero heading', () => {
    render(<LandingPage />)
    const heading = screen.getByRole('heading', { level: 1 })
    expect(heading.textContent).toMatch(/Do you\s+understand/)
    expect(heading.textContent).toMatch(/the code you ship\?/)
  })

  test('renders hero tagline badge', () => {
    render(<LandingPage />)
    expect(screen.getByText(/For teams shipping AI-generated code/)).toBeTruthy()
  })

  test('renders two Install GitHub App CTA links (hero + bottom)', () => {
    render(<LandingPage />)
    const links = screen.getAllByRole('link', { name: /install github app/i })
    expect(links.length).toBe(2)
  })

  test('all CTA links point to GitHub App install URL', () => {
    render(<LandingPage />)
    const links = screen.getAllByRole('link', { name: /install github app/i })
    for (const link of links) {
      expect(link.getAttribute('href')).toContain('github.com/apps/')
      expect(link.getAttribute('href')).toContain('/installations/new')
    }
  })

  test('renders "How it works" section with 3 steps', () => {
    render(<LandingPage />)
    expect(screen.getByText('Three steps to comprehension')).toBeTruthy()
    expect(screen.getByText('PR opened')).toBeTruthy()
    expect(screen.getByText('Answer Socratic questions')).toBeTruthy()
    expect(screen.getByText('Get your score')).toBeTruthy()
  })

  test('renders terminal-like visuals for each step', () => {
    const { container } = render(<LandingPage />)
    const text = container.textContent ?? ''
    expect(text).toContain('PR #42')
    expect(text).toContain('recursive approach here')
    expect(text).toContain('strong')
  })

  test('renders BYOK / privacy section', () => {
    render(<LandingPage />)
    expect(screen.getByText('Your keys, your data, your control')).toBeTruthy()
    expect(screen.getByText('Bring Your Own Key')).toBeTruthy()
    expect(screen.getByText('Ephemeral containers')).toBeTruthy()
    expect(screen.getByText('Private by default')).toBeTruthy()
  })

  test('does not mention free or open-source', () => {
    const { container } = render(<LandingPage />)
    const text = container.textContent?.toLowerCase() ?? ''
    expect(text).not.toContain('open-source')
    expect(text).not.toContain('open source')
    expect(text).not.toContain('mit licensed')
    // "free" can appear in "free" standalone but not as a selling point
    expect(text).not.toContain('free &')
    expect(text).not.toContain('free and')
  })

  test('renders social proof section with stats', () => {
    render(<LandingPage />)
    expect(screen.getByText(/Comprehension debt/)).toBeTruthy()
    expect(screen.getByText('5-7x')).toBeTruthy()
    expect(screen.getByText('Self-hosted')).toBeTruthy()
  })

  test('renders sign-in link in header', () => {
    render(<LandingPage />)
    const signIn = screen.getByRole('link', { name: /sign in/i })
    expect(signIn.getAttribute('href')).toContain('/api/v1/auth/github')
  })

  test('renders footer with GitHub link', () => {
    render(<LandingPage />)
    const ghLink = screen.getByRole('link', { name: /^GitHub$/ })
    expect(ghLink.getAttribute('href')).toContain('github.com/mariuspruvot/helprs')
    expect(ghLink.getAttribute('target')).toBe('_blank')
  })

  test('hero heading uses responsive text size classes', () => {
    render(<LandingPage />)
    const heading = screen.getByRole('heading', { level: 1 })
    expect(heading.className).toContain('text-[32px]')
    expect(heading.className).toContain('md:text-[40px]')
    expect(heading.className).toContain('lg:text-[52px]')
  })

  test('CTA in hero is full-width on small screens', () => {
    render(<LandingPage />)
    const links = screen.getAllByRole('link', { name: /install github app/i })
    expect(links[0].className).toContain('w-full')
  })
})
