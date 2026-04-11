import React from 'react'
import { act, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

// apiFetch is the only network seam — mock it for every ChatView test.
// API_BASE is also exported (used by ChatPanel to build the SSE URL),
// so the mock must include it or imports of it will be undefined.
vi.mock('../../shared/api/client', () => ({
  apiFetch: vi.fn(),
  API_BASE: 'http://localhost:8000',
}))

// react-resizable-panels relies on ResizeObserver and layout measurements that
// jsdom does not provide. Per Dev Notes §Testing: a minimal render-through
// stub is acceptable as long as we preserve the separator's role so the
// component test can still assert layout mode.
vi.mock('react-resizable-panels', () => {
  const Group = ({ children, className }: { children?: React.ReactNode; className?: string }) =>
    React.createElement('div', { className, 'data-group': true }, children)
  const Panel = ({
    children,
    className,
    'data-testid': testId,
  }: {
    children?: React.ReactNode
    className?: string
    ['data-testid']?: string
  }) =>
    React.createElement('div', { className, 'data-panel': true, 'data-testid': testId }, children)
  const Separator = ({
    children,
    className,
    'data-testid': testId,
  }: {
    children?: React.ReactNode
    className?: string
    ['data-testid']?: string
  }) =>
    React.createElement(
      'div',
      {
        className,
        role: 'separator',
        'aria-orientation': 'vertical',
        tabIndex: 0,
        'data-testid': testId,
      },
      children,
    )
  return { Group, Panel, Separator }
})

import { apiFetch } from '../../shared/api/client'
import ChatView from './ChatView'
import { useSessionStore } from './store'
import {
  SESSION_ID,
  makeSession,
  mockApiFetchOnce,
  renderAtSessionRoute,
  resetStores,
  setWindowWidth,
} from './__testUtils'

const mockedApiFetch = vi.mocked(apiFetch)

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

beforeEach(() => {
  setWindowWidth(1400)
  resetStores()
  mockedApiFetch.mockReset()
})

afterEach(() => {
  cleanup()
})

describe('ChatView — data loading', () => {
  test('renders session header, split layout, and first file tab active on happy path', async () => {
    mockApiFetchOnce(mockedApiFetch, jsonResponse(makeSession()))

    renderAtSessionRoute(<ChatView />)

    // Wait for the query to resolve and the layout to render.
    await waitFor(() => {
      expect(screen.getByTestId('session-header')).toBeTruthy()
    })

    // Header fields.
    expect(screen.getByTestId('session-header-repo').textContent).toBe('acme/helprs')
    expect(screen.getByTestId('session-header-pr-title').textContent).toBe('Improve caching')
    expect(screen.getByTestId('session-header-role-badge').textContent).toBe('AUTHOR')
    // Story 3.3 progress indicator: zero committed messages yet, total 3.
    const progress = screen.getByTestId('session-header-progress')
    expect(progress.textContent).toBe('Question 0 of 3')
    expect(progress.getAttribute('aria-live')).toBe('polite')
    expect(screen.getByTestId('session-header-ai-disclaimer').textContent).toContain(
      'AI-generated content may be inaccurate',
    )

    // Split layout — the separator (resize handle) is rendered.
    expect(screen.getByTestId('session-resize-handle')).toBeTruthy()
    expect(screen.getByTestId('chat-panel')).toBeTruthy()
    expect(screen.getByTestId('diff-viewer')).toBeTruthy()

    // First file tab is active.
    const firstTab = screen.getByTestId('diff-file-tab-0')
    expect(firstTab.getAttribute('aria-selected')).toBe('true')
  })

  test('renders 403 error screen when fetch returns 403', async () => {
    mockApiFetchOnce(mockedApiFetch, new Response(null, { status: 403 }))

    renderAtSessionRoute(<ChatView />)

    await waitFor(() => {
      expect(screen.getByText('No access')).toBeTruthy()
    })
    expect(
      screen.getByText(/You do not have access to this session's repository\./),
    ).toBeTruthy()
  })

  test('renders 404 error screen when fetch returns 404', async () => {
    mockApiFetchOnce(mockedApiFetch, new Response(null, { status: 404 }))

    renderAtSessionRoute(<ChatView />)

    await waitFor(() => {
      expect(screen.getByText('Session not found')).toBeTruthy()
    })
  })

  test('renders 422 error screen with no Retry button when fetch returns 422', async () => {
    mockApiFetchOnce(mockedApiFetch, new Response(null, { status: 422 }))

    renderAtSessionRoute(<ChatView />)

    await waitFor(() => {
      expect(screen.getByText('Invalid session ID')).toBeTruthy()
    })
    expect(
      screen.getByText(/This session link is malformed\. Check the URL and try again\./),
    ).toBeTruthy()
    // 422 is a URL problem — retrying would not help, so no Retry button.
    expect(screen.queryByRole('button', { name: /retry/i })).toBeNull()
  })

  test('renders 429 error screen with no Retry button when fetch returns 429', async () => {
    mockApiFetchOnce(mockedApiFetch, new Response(null, { status: 429 }))

    renderAtSessionRoute(<ChatView />)

    await waitFor(() => {
      expect(screen.getByText('Rate limit exceeded')).toBeTruthy()
    })
    expect(
      screen.getByText(/Too many requests\. Please wait a moment before trying again\./),
    ).toBeTruthy()
    // 429 deliberately has no Retry button — hammering the limiter is worse.
    expect(screen.queryByRole('button', { name: /retry/i })).toBeNull()
  })

  test('renders retryable error screen on 500 and Retry triggers a new fetch', async () => {
    // useSession retries 5xx twice (failureCount < 2), so 3 total attempts
    // before the query enters error state. We queue one extra 500 for the
    // Retry click.
    mockedApiFetch.mockResolvedValue(new Response(null, { status: 500 }))

    renderAtSessionRoute(<ChatView />)

    await waitFor(
      () => {
        expect(screen.getByText('Temporarily unavailable')).toBeTruthy()
      },
      { timeout: 5000 },
    )

    const retryButton = screen.getByText('Retry')
    const callsBefore = mockedApiFetch.mock.calls.length
    fireEvent.click(retryButton)

    await waitFor(() => {
      expect(mockedApiFetch.mock.calls.length).toBeGreaterThan(callsBefore)
    })
  })
})

describe('ChatView — responsive breakpoints', () => {
  test('collapses to tabbed layout below 1100px', async () => {
    setWindowWidth(900)
    mockApiFetchOnce(mockedApiFetch, jsonResponse(makeSession()))

    renderAtSessionRoute(<ChatView />)

    await waitFor(() => {
      expect(screen.getByTestId('session-header')).toBeTruthy()
    })

    expect(screen.getByTestId('tabbed-layout')).toBeTruthy()
    expect(screen.queryByTestId('session-resize-handle')).toBeNull()
    // tablist is rendered.
    expect(screen.getByRole('tablist', { name: 'Session view' })).toBeTruthy()
  })

  test('collapses to mobile layout below 768px', async () => {
    setWindowWidth(500)
    mockApiFetchOnce(mockedApiFetch, jsonResponse(makeSession()))

    renderAtSessionRoute(<ChatView />)

    await waitFor(() => {
      expect(screen.getByTestId('mobile-layout')).toBeTruthy()
    })

    expect(screen.getByTestId('mobile-banner').textContent).toContain(
      'Open on desktop for the full experience with code view.',
    )
    expect(screen.queryByTestId('diff-viewer')).toBeNull()
    expect(screen.queryByTestId('session-resize-handle')).toBeNull()
  })
})

describe('ChatView — file tab interaction', () => {
  test('clicking the second file tab updates activeFileIndex in the store', async () => {
    mockApiFetchOnce(mockedApiFetch, jsonResponse(makeSession()))

    renderAtSessionRoute(<ChatView />)

    await waitFor(() => {
      expect(screen.getByTestId('diff-file-tab-1')).toBeTruthy()
    })

    const secondTab = screen.getByTestId('diff-file-tab-1')
    fireEvent.click(secondTab)

    await waitFor(() => {
      expect(useSessionStore.getState().activeFileIndex).toBe(1)
    })
    expect(secondTab.getAttribute('aria-selected')).toBe('true')
  })
})

describe('ChatView — useSession URL', () => {
  test('calls the backend with the session id from the URL', async () => {
    mockApiFetchOnce(mockedApiFetch, jsonResponse(makeSession()))

    renderAtSessionRoute(<ChatView />)

    await waitFor(() => {
      expect(mockedApiFetch).toHaveBeenCalled()
    })
    expect(mockedApiFetch.mock.calls[0]?.[0]).toBe(`/api/v1/sessions/${SESSION_ID}`)
  })

  test('clearSession runs on unmount', async () => {
    mockApiFetchOnce(mockedApiFetch, jsonResponse(makeSession()))

    const { unmount } = renderAtSessionRoute(<ChatView />)
    await waitFor(() => {
      expect(useSessionStore.getState().session).not.toBeNull()
    })

    act(() => {
      unmount()
    })
    expect(useSessionStore.getState().session).toBeNull()
  })
})
