import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

// Mock react-router before any imports that use it
const mockNavigate = vi.fn()
vi.mock('react-router', () => ({
  useNavigate: () => mockNavigate,
}))

const mockApiFetch = vi.fn()
const mockRefreshToken = vi.fn()
vi.mock('../../shared/api/client', () => ({
  apiFetch: (...args: unknown[]) => mockApiFetch(...args),
  refreshToken: () => mockRefreshToken(),
}))

// Import after mocks
import OAuthCallback from './OAuthCallback'
import { useAuthStore } from './store'

const FAKE_USER = {
  id: '1',
  github_id: 123,
  github_login: 'testuser',
  email: null,
  avatar_url: null,
  created_at: '2026-01-01',
}

beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.setState({
    accessToken: null,
    user: null,
    isAuthenticated: false,
    returnUrl: null,
  })
  sessionStorage.clear()
})

afterEach(() => {
  cleanup()
})

describe('OAuthCallback', () => {
  test('shows authenticating message', () => {
    mockRefreshToken.mockResolvedValue('test-token')
    mockApiFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve(FAKE_USER) })

    render(<OAuthCallback />)

    expect(screen.getByText('Authenticating...')).toBeTruthy()
  })

  test('trades the refresh cookie for a token, then fetches the user', async () => {
    // The backend no longer puts the access token in the redirect URL, where
    // it landed in browser history, Referer and proxy logs.
    mockRefreshToken.mockResolvedValue('test-token')
    mockApiFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve(FAKE_USER) })

    render(<OAuthCallback />)

    await vi.waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith('/api/v1/auth/me')
    })
    await vi.waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true })
    })

    expect(mockRefreshToken).toHaveBeenCalled()
    expect(useAuthStore.getState().isAuthenticated).toBe(true)
    expect(useAuthStore.getState().accessToken).toBe('test-token')
  })

  test('the token comes from the cookie exchange, not the URL', async () => {
    mockRefreshToken.mockResolvedValue('cookie-token')
    mockApiFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve(FAKE_USER) })

    render(<OAuthCallback />)

    await vi.waitFor(() => {
      expect(useAuthStore.getState().accessToken).toBe('cookie-token')
    })
  })

  test('navigates to returnUrl from sessionStorage after login', async () => {
    sessionStorage.setItem('helprs.returnUrl', '/installations/123/settings')
    mockRefreshToken.mockResolvedValue('test-token')
    mockApiFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve(FAKE_USER) })

    render(<OAuthCallback />)

    await vi.waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/installations/123/settings', { replace: true })
    })
  })

  test('redirects to / when there is no session to trade', async () => {
    mockRefreshToken.mockResolvedValue(null)

    render(<OAuthCallback />)

    await vi.waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true })
    })
    expect(mockApiFetch).not.toHaveBeenCalled()
  })

  test('redirects to / on fetch failure', async () => {
    mockRefreshToken.mockResolvedValue('test-token')
    mockApiFetch.mockResolvedValue({ ok: false })

    render(<OAuthCallback />)

    await vi.waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true })
    })
  })

  test('redirects to / on network error', async () => {
    mockRefreshToken.mockRejectedValue(new Error('Network error'))

    render(<OAuthCallback />)

    await vi.waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true })
    })
  })
})
