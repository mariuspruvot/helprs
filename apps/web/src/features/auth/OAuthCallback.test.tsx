import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

// Mock react-router before any imports that use it
const mockNavigate = vi.fn()
let mockSearchParams = new URLSearchParams()
vi.mock('react-router', () => ({
  useNavigate: () => mockNavigate,
  useSearchParams: () => [mockSearchParams],
}))

// Mock apiFetch
const mockApiFetch = vi.fn()
vi.mock('../../shared/api/client', () => ({
  apiFetch: (...args: unknown[]) => mockApiFetch(...args),
}))

// Import after mocks
import OAuthCallback from './OAuthCallback'
import { useAuthStore } from './store'

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
  test('redirects to / when no access_token in params', () => {
    mockSearchParams = new URLSearchParams()
    render(<OAuthCallback />)

    expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true })
  })

  test('shows authenticating message', () => {
    mockSearchParams = new URLSearchParams('access_token=test-token')
    mockApiFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ id: '1', github_login: 'testuser' }) })
    render(<OAuthCallback />)

    expect(screen.getByText('Authenticating...')).toBeTruthy()
  })

  test('calls login and fetches user on valid token', async () => {
    mockSearchParams = new URLSearchParams('access_token=test-token')
    const fakeUser = { id: '1', github_id: 123, github_login: 'testuser', email: null, avatar_url: null, created_at: '2026-01-01' }
    mockApiFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve(fakeUser) })

    render(<OAuthCallback />)

    // Wait for async effects
    await vi.waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith('/api/v1/auth/me')
    })

    await vi.waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true })
    })

    expect(useAuthStore.getState().isAuthenticated).toBe(true)
    expect(useAuthStore.getState().accessToken).toBe('test-token')
  })

  test('navigates to returnUrl from sessionStorage after login', async () => {
    sessionStorage.setItem('helprs.returnUrl', '/installations/123/settings')
    mockSearchParams = new URLSearchParams('access_token=test-token')
    const fakeUser = { id: '1', github_id: 123, github_login: 'testuser', email: null, avatar_url: null, created_at: '2026-01-01' }
    mockApiFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve(fakeUser) })

    render(<OAuthCallback />)

    await vi.waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/installations/123/settings', { replace: true })
    })
  })

  test('redirects to / on fetch failure', async () => {
    mockSearchParams = new URLSearchParams('access_token=bad-token')
    mockApiFetch.mockResolvedValue({ ok: false })

    render(<OAuthCallback />)

    await vi.waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true })
    })
  })

  test('redirects to / on network error', async () => {
    mockSearchParams = new URLSearchParams('access_token=test-token')
    mockApiFetch.mockRejectedValue(new Error('Network error'))

    render(<OAuthCallback />)

    await vi.waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true })
    })
  })
})
