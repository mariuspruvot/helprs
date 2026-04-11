/**
 * Unit tests for `useSSE`.
 *
 * We install a minimal global `EventSource` shim so the tests drive the
 * hook deterministically — no network, no timers beyond what the shim
 * itself exposes. Each test constructs a shim, mounts the hook via
 * `renderHook`, dispatches scripted events, and asserts the matching
 * callback fired with the expected payload.
 *
 * Exponential backoff timing is NOT tested end-to-end (brittle + low
 * value). One test locks the "reconnects after close" state machine
 * using fake timers.
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useSSE } from './useSSE'

interface ShimListener {
  type: string
  handler: (event: Event | MessageEvent) => void
}

class ShimEventSource {
  static instances: ShimEventSource[] = []
  static readonly CLOSED = 2
  static readonly OPEN = 1
  static readonly CONNECTING = 0

  readonly url: string
  readonly withCredentials: boolean
  readyState: number = ShimEventSource.CONNECTING
  private listeners: ShimListener[] = []
  closed = false

  constructor(url: string, init?: { withCredentials?: boolean }) {
    this.url = url
    this.withCredentials = init?.withCredentials ?? false
    ShimEventSource.instances.push(this)
  }

  addEventListener(type: string, handler: (event: Event | MessageEvent) => void): void {
    this.listeners.push({ type, handler })
  }

  dispatch(type: string, data?: string): void {
    const event = new MessageEvent(type, { data: data ?? '' })
    for (const l of this.listeners) {
      if (l.type === type) l.handler(event)
    }
  }

  /** Simulate an SSE `open` event. */
  openConnection(): void {
    this.readyState = ShimEventSource.OPEN
    this.dispatch('open')
  }

  /** Simulate a network-level failure — marks CLOSED and fires error. */
  fail(): void {
    this.readyState = ShimEventSource.CLOSED
    const event = new Event('error')
    for (const l of this.listeners) {
      if (l.type === 'error') l.handler(event)
    }
  }

  close(): void {
    this.closed = true
    this.readyState = ShimEventSource.CLOSED
  }
}

describe('useSSE', () => {
  beforeEach(() => {
    ShimEventSource.instances = []
    // @ts-expect-error — jsdom does not ship EventSource
    globalThis.EventSource = ShimEventSource
  })

  afterEach(() => {
    vi.useRealTimers()
    // @ts-expect-error — cleanup
    delete globalThis.EventSource
  })

  it('opens an EventSource against the given URL with credentials', () => {
    renderHook(() => useSSE({ url: '/api/v1/sessions/abc/stream' }))
    expect(ShimEventSource.instances).toHaveLength(1)
    const es = ShimEventSource.instances[0]!
    expect(es.url).toBe('/api/v1/sessions/abc/stream')
    expect(es.withCredentials).toBe(true)
  })

  it('does not open when enabled=false', () => {
    renderHook(() => useSSE({ url: '/api/v1/sessions/abc/stream', enabled: false }))
    expect(ShimEventSource.instances).toHaveLength(0)
  })

  it('fires onQuestionToken with parsed payload', () => {
    const onQuestionToken = vi.fn()
    renderHook(() => useSSE({ url: '/sse', onQuestionToken }))

    const es = ShimEventSource.instances[0]!
    act(() => {
      es.dispatch(
        'question_token',
        JSON.stringify({ question_id: 'q1', token: 'Hello', number: 1, total: 3 }),
      )
    })
    expect(onQuestionToken).toHaveBeenCalledWith({
      questionId: 'q1',
      token: 'Hello',
      number: 1,
      total: 3,
    })
  })

  it('fires onQuestion with the raw payload shape', () => {
    const onQuestion = vi.fn()
    renderHook(() => useSSE({ url: '/sse', onQuestion }))

    const payload = {
      question_id: 'q1',
      text: 'Why?',
      number: 1,
      total: 3,
      file_refs: ['foo.ts'],
    }
    const es = ShimEventSource.instances[0]!
    act(() => {
      es.dispatch('question', JSON.stringify(payload))
    })
    expect(onQuestion).toHaveBeenCalledWith(payload)
  })

  it('fires onDone with camelCased payload', () => {
    const onDone = vi.fn()
    renderHook(() => useSSE({ url: '/sse', onDone }))
    const es = ShimEventSource.instances[0]!
    act(() => {
      es.dispatch(
        'done',
        JSON.stringify({ session_id: 's1', question_count: 3 }),
      )
    })
    expect(onDone).toHaveBeenCalledWith({ sessionId: 's1', questionCount: 3 })
  })

  it('fires onError with kind=parse on malformed JSON', () => {
    const onError = vi.fn()
    renderHook(() => useSSE({ url: '/sse', onError }))
    const es = ShimEventSource.instances[0]!
    act(() => {
      es.dispatch('question_token', 'not-json')
    })
    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'parse' }),
    )
  })

  it('closes the source on unmount', () => {
    const { unmount } = renderHook(() => useSSE({ url: '/sse' }))
    const es = ShimEventSource.instances[0]!
    unmount()
    expect(es.closed).toBe(true)
  })

  it('closes the source when enabled toggles to false', () => {
    const { rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) => useSSE({ url: '/sse', enabled }),
      { initialProps: { enabled: true } },
    )
    const es = ShimEventSource.instances[0]!
    rerender({ enabled: false })
    expect(es.closed).toBe(true)
  })

  it('schedules a reconnection after a network failure', () => {
    vi.useFakeTimers()
    renderHook(() => useSSE({ url: '/api/v1/sessions/abc/stream' }))
    expect(ShimEventSource.instances).toHaveLength(1)
    const first = ShimEventSource.instances[0]!
    act(() => {
      first.fail()
    })
    // The hook schedules a reconnect via setTimeout (500 ms for attempt 0).
    act(() => {
      vi.advanceTimersByTime(500)
    })
    // P20 from story-3.3 review: assert the reconnect targets the
    // SAME URL with the SAME `withCredentials` setting. The old
    // assertion only checked instance count, which would pass even
    // if the reconnect hit the wrong URL or dropped cookie auth.
    expect(ShimEventSource.instances.length).toBeGreaterThanOrEqual(2)
    const second = ShimEventSource.instances[1]!
    expect(second.url).toBe(first.url)
    expect(second.withCredentials).toBe(true)
    // And the first instance was closed before the second opened
    // (P3 — no zombie EventSource).
    expect(first.closed).toBe(true)
  })

  it('does not reconnect after a server-framed `error` frame (P1/P2)', () => {
    vi.useFakeTimers()
    const onError = vi.fn()
    renderHook(() => useSSE({ url: '/sse', onError }))
    expect(ShimEventSource.instances).toHaveLength(1)
    const first = ShimEventSource.instances[0]!

    // Dispatch a server-framed error via a MessageEvent (event.data
    // is a JSON string — our shim's dispatch() creates a MessageEvent
    // for the 'error' type too so the hook's data-presence check fires).
    act(() => {
      first.dispatch('error', JSON.stringify({ error: 'boom', retryable: false }))
    })

    // onError fired with kind=server.
    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'server' }),
    )

    // Now simulate the backend closing the connection after the
    // error frame — which in a real browser fires a native `error`
    // event with readyState === CLOSED. The hook MUST NOT reconnect.
    act(() => {
      first.fail()
    })
    act(() => {
      vi.advanceTimersByTime(60_000)
    })
    // Still exactly one instance — no zombie reconnect.
    expect(ShimEventSource.instances).toHaveLength(1)
  })

  it('does not reconnect after a `done` frame (P2)', () => {
    vi.useFakeTimers()
    const onDone = vi.fn()
    renderHook(() => useSSE({ url: '/sse', onDone }))
    expect(ShimEventSource.instances).toHaveLength(1)
    const first = ShimEventSource.instances[0]!

    act(() => {
      first.dispatch(
        'done',
        JSON.stringify({ session_id: 's1', question_count: 3 }),
      )
    })
    expect(onDone).toHaveBeenCalledWith({ sessionId: 's1', questionCount: 3 })

    // Server closes the connection after done → native error fires.
    act(() => {
      first.fail()
    })
    act(() => {
      vi.advanceTimersByTime(60_000)
    })
    // No reconnect — the hook marked the stream terminal on `done`.
    expect(ShimEventSource.instances).toHaveLength(1)
  })

  it('forwards a malformed `question` frame as a server-kind error (P5)', () => {
    const onQuestion = vi.fn()
    const onError = vi.fn()
    renderHook(() => useSSE({ url: '/sse', onQuestion, onError }))
    const es = ShimEventSource.instances[0]!

    // Missing `file_refs` → old code crashed the caller on .length.
    act(() => {
      es.dispatch(
        'question',
        JSON.stringify({
          question_id: 'q1',
          text: 'Why?',
          number: 1,
          total: 3,
        }),
      )
    })
    // Caller is never invoked with a bad payload.
    expect(onQuestion).not.toHaveBeenCalled()
    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'server' }),
    )
  })
})
