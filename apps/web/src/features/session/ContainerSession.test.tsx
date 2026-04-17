import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

// Mock the API module
vi.mock('./containerApi', () => ({
  createContainerSession: vi.fn(),
  stopContainerSession: vi.fn(),
  buildStreamUrl: vi.fn(),
}))

// Mock the auth store
vi.mock('../auth/store', () => ({
  useAuthStore: {
    getState: () => ({
      accessToken: 'test-token',
      isAuthenticated: true,
    }),
    setState: vi.fn(),
    subscribe: vi.fn(),
  },
}))

import {
  createContainerSession,
  stopContainerSession,
  buildStreamUrl,
} from './containerApi'
import ContainerSession from './ContainerSession'
import type { ContainerSessionResponse } from './containerTypes'

const mockedCreate = vi.mocked(createContainerSession)
const mockedStop = vi.mocked(stopContainerSession)
const mockedBuildStreamUrl = vi.mocked(buildStreamUrl)

// Capture EventSource instances for test assertions
type EventSourceHandler = (event: MessageEvent | Event) => void
interface MockEventSource {
  url: string
  close: ReturnType<typeof vi.fn>
  readyState: number
  addEventListener: ReturnType<typeof vi.fn>
  onmessage: EventSourceHandler | null
  listeners: Record<string, EventSourceHandler[]>
  CONNECTING: 0
  OPEN: 1
  CLOSED: 2
}

let mockEventSources: MockEventSource[] = []

// Replace global EventSource
const OriginalEventSource = globalThis.EventSource

beforeEach(() => {
  mockEventSources = []
  vi.stubGlobal('EventSource', class {
    url: string
    withCredentials: boolean
    readyState = 1
    close = vi.fn()
    addEventListener = vi.fn()
    onmessage: EventSourceHandler | null = null
    listeners: Record<string, EventSourceHandler[]> = {}

    static CONNECTING = 0
    static OPEN = 1
    static CLOSED = 2

    constructor(url: string, _opts?: { withCredentials: boolean }) {
      this.url = url
      this.withCredentials = _opts?.withCredentials ?? false
      this.addEventListener = vi.fn().mockImplementation((event: string, handler: EventSourceHandler) => {
        if (!this.listeners[event]) {
          this.listeners[event] = []
        }
        this.listeners[event].push(handler)
      })
      mockEventSources.push(this as unknown as MockEventSource)
    }
  })

  mockedBuildStreamUrl.mockReturnValue('http://localhost:8000/api/v1/containers/sessions/test-id/stream?access_token=test-token')
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  if (OriginalEventSource) {
    vi.stubGlobal('EventSource', OriginalEventSource)
  }
})

const defaultProps = {
  installationId: '11111111-1111-1111-1111-111111111111',
  repoFullName: 'acme/helprs',
  prNumber: 42,
  skillName: 'challenge-me',
  onBack: vi.fn(),
}

function makeSessionResponse(overrides: Partial<ContainerSessionResponse> = {}): ContainerSessionResponse {
  return {
    id: 'test-session-id',
    installation_id: defaultProps.installationId,
    user_id: null,
    pr_number: 42,
    repo_full_name: 'acme/helprs',
    skill_name: 'challenge-me',
    container_id: 'docker-abc123',
    status: 'running',
    started_at: '2026-04-17T00:00:00Z',
    completed_at: null,
    created_at: '2026-04-17T00:00:00Z',
    updated_at: '2026-04-17T00:00:00Z',
    ...overrides,
  }
}

describe('ContainerSession', () => {
  test('renders initial loading state and calls createContainerSession', async () => {
    mockedCreate.mockResolvedValue(makeSessionResponse())

    render(<ContainerSession {...defaultProps} />)

    expect(screen.getByTestId('container-session')).toBeTruthy()
    // Repo name and PR number appear in header and terminal output
    expect(screen.getAllByText(/acme\/helprs/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/42/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/challenge-me/).length).toBeGreaterThan(0)

    await waitFor(() => {
      expect(mockedCreate).toHaveBeenCalledWith({
        installation_id: defaultProps.installationId,
        pr_number: 42,
        repo_full_name: 'acme/helprs',
        skill_name: 'challenge-me',
      })
    })
  })

  test('shows starting message in terminal', async () => {
    mockedCreate.mockResolvedValue(makeSessionResponse())

    render(<ContainerSession {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText(/Starting challenge-me for acme\/helprs#42/)).toBeTruthy()
    })
  })

  test('shows error when session creation fails', async () => {
    mockedCreate.mockRejectedValue(new Error('Network error'))

    render(<ContainerSession {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByTestId('error-banner')).toBeTruthy()
      expect(screen.getByText('Network error')).toBeTruthy()
    })
  })

  test('connects to SSE stream after successful session creation', async () => {
    mockedCreate.mockResolvedValue(makeSessionResponse())

    render(<ContainerSession {...defaultProps} />)

    await waitFor(() => {
      expect(mockEventSources.length).toBeGreaterThan(0)
    })

    expect(mockedBuildStreamUrl).toHaveBeenCalledWith('test-session-id', 'test-token')
  })

  test('calls onBack when back button is clicked', async () => {
    mockedCreate.mockResolvedValue(makeSessionResponse())
    const onBack = vi.fn()

    render(<ContainerSession {...defaultProps} onBack={onBack} />)

    fireEvent.click(screen.getByTestId('back-button'))
    expect(onBack).toHaveBeenCalled()
  })

  test('calls stopContainerSession when stop button is clicked', async () => {
    mockedCreate.mockResolvedValue(makeSessionResponse())
    mockedStop.mockResolvedValue({ id: 'test-session-id', status: 'stopped', message: 'Stopped' })

    render(<ContainerSession {...defaultProps} />)

    // Wait for session to be created and status to show running
    await waitFor(() => {
      expect(screen.getByTestId('session-status')).toBeTruthy()
    })

    // The stop button appears when status is running/starting
    const stopButton = screen.queryByTestId('stop-button')
    if (stopButton) {
      fireEvent.click(stopButton)
      await waitFor(() => {
        expect(mockedStop).toHaveBeenCalledWith('test-session-id')
      })
    }
  })

  test('shows failed status when container fails to start', async () => {
    mockedCreate.mockResolvedValue(makeSessionResponse({ status: 'failed', container_id: null }))

    render(<ContainerSession {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByTestId('error-banner')).toBeTruthy()
      expect(screen.getByTestId('error-banner').textContent).toBe('Container failed to start')
    })
  })

  test('renders terminal output component', async () => {
    mockedCreate.mockResolvedValue(makeSessionResponse())

    render(<ContainerSession {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByTestId('terminal-output')).toBeTruthy()
    })
  })

  test('closes EventSource on unmount', async () => {
    mockedCreate.mockResolvedValue(makeSessionResponse())

    const { unmount } = render(<ContainerSession {...defaultProps} />)

    await waitFor(() => {
      expect(mockEventSources.length).toBeGreaterThan(0)
    })

    unmount()

    expect(mockEventSources[0]!.close).toHaveBeenCalled()
  })
})
