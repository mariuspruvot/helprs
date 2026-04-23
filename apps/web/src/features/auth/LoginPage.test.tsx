import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, test } from 'vitest'
import LoginPage from './LoginPage'

afterEach(() => cleanup())

describe('LoginPage', () => {
  test('renders helPRs wordmark', () => {
    render(<LoginPage />)
    expect(screen.getByText('helPRs')).toBeTruthy()
  })

  test('renders sign-in link pointing to GitHub OAuth', () => {
    render(<LoginPage />)
    const link = screen.getByRole('link', { name: /sign in with github/i })
    expect(link.getAttribute('href')).toContain('/api/v1/auth/github')
  })

  test('renders link to the GitHub repo', () => {
    render(<LoginPage />)
    const link = screen.getByRole('link', { name: /view on github/i })
    expect(link.getAttribute('href')).toContain('github.com/mariuspruvot/helprs')
  })

  test('renders tagline', () => {
    const { container } = render(<LoginPage />)
    expect(container.textContent).toContain('Self-hosted')
  })
})
