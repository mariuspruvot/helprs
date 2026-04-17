import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { useAuthStore } from './store'

// Capture window.location.href assignments
const locationHrefSpy = vi.fn()
const originalLocation = window.location

beforeEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
  // Mock window.location
  Object.defineProperty(window, 'location', {
    value: { ...originalLocation, pathname: '/installations/42/settings', search: '', href: '' },
    writable: true,
    configurable: true,
  })
  Object.defineProperty(window.location, 'href', {
    set: locationHrefSpy,
    get: () => '',
    configurable: true,
  })
})

afterEach(() => {
  cleanup()
  Object.defineProperty(window, 'location', { value: originalLocation, writable: true, configurable: true })
})

// Import after setup
import ProtectedRoute, { RETURN_URL_STORAGE_KEY } from './ProtectedRoute'

describe('ProtectedRoute', () => {
  test('renders children when authenticated', () => {
    useAuthStore.setState({ isAuthenticated: true, accessToken: 'token' })

    render(
      <ProtectedRoute>
        <div data-testid="protected-content">Secret content</div>
      </ProtectedRoute>
    )

    expect(screen.getByTestId('protected-content')).toBeTruthy()
    expect(screen.getByText('Secret content')).toBeTruthy()
  })

  test('shows redirect message when not authenticated', () => {
    useAuthStore.setState({ isAuthenticated: false, accessToken: null })

    render(
      <ProtectedRoute>
        <div>Secret content</div>
      </ProtectedRoute>
    )

    expect(screen.getByText('Redirecting to login...')).toBeTruthy()
    expect(screen.queryByText('Secret content')).toBeNull()
  })

  test('redirects to GitHub OAuth when not authenticated', () => {
    useAuthStore.setState({ isAuthenticated: false, accessToken: null })

    render(
      <ProtectedRoute>
        <div>Secret content</div>
      </ProtectedRoute>
    )

    expect(locationHrefSpy).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/auth/github')
    )
  })

  test('persists returnUrl to sessionStorage when not authenticated', () => {
    useAuthStore.setState({ isAuthenticated: false, accessToken: null })

    render(
      <ProtectedRoute>
        <div>Secret content</div>
      </ProtectedRoute>
    )

    expect(sessionStorage.getItem(RETURN_URL_STORAGE_KEY)).toBe('/installations/42/settings')
  })

  test('exports RETURN_URL_STORAGE_KEY constant', () => {
    expect(RETURN_URL_STORAGE_KEY).toBe('helprs.returnUrl')
  })
})
