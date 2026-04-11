/**
 * Story 3.4 P11 (code-review A2): integration test for the answer
 * submission flow inside ChatPanel. The spec AC#16 originally called
 * for a standalone `submitAnswer.test.tsx`; Story 3.4 D3 (code-review
 * decision) merges it into this integration test because `submitAnswer`
 * is inlined in ChatPanel and depends on 7+ closure refs, so extracting
 * a pure helper would be worse than the test-coverage gap.
 *
 * Covered cases:
 *   1. Happy path — POST → token stream → feedback commit → done →
 *      input re-enabled.
 *   2. Error path — HTTP 409 → error banner + input re-enabled.
 *   3. Resume-from-progress — session.progress seeds placeholder
 *      messages for answered cycles.
 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi, type Mock } from 'vitest'

import { useAuthStore } from '../auth/store'
import ChatPanel from './ChatPanel'
import { useSessionStore } from './store'
import { makeSession, resetStores } from './__testUtils'

// Mock useSSE so GET-side streaming is a no-op in these tests — we
// only care about the POST /answers + feedback stream.
vi.mock('../../shared/hooks/useSSE', () => ({
  useSSE: () => ({ status: 'open' }),
}))

// Mock consumeSSEStream so tests can script the feedback event
// sequence without needing a real fetch.body reader.
let scriptedEvents: Array<[string, unknown]> = []

vi.mock('../../shared/hooks/parseSSE', () => ({
  consumeSSEStream: async (
    _reader: unknown,
    handlers: { onEvent: (event: string, data: unknown) => void; onError: (err: Error) => void },
  ) => {
    for (const [event, data] of scriptedEvents) {
      handlers.onEvent(event, data)
    }
  },
}))

let fetchMock: Mock

beforeEach(() => {
  resetStores()
  useAuthStore.setState({ accessToken: 'jwt-test', isAuthenticated: true })
  scriptedEvents = []
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function seedPendingQuestion(): void {
  // Push a single committed ai_question so the submit helper has a
  // current question to pair with.
  useSessionStore.setState({
    messages: [
      {
        id: 'q1',
        kind: 'ai_question',
        questionNumber: 1,
        total: 3,
        text: 'Why does foo call bar?',
        fileRefs: [],
        createdAt: '2026-04-11T00:00:00Z',
        isStreaming: false,
      },
    ],
  })
}

function mockFetchOk(): void {
  fetchMock.mockResolvedValue({
    ok: true,
    status: 200,
    body: new ReadableStream(),
  } as unknown as Response)
}

function submitAnswer(text: string): void {
  const textarea = screen.getByTestId('answer-input-textarea') as HTMLTextAreaElement
  fireEvent.change(textarea, { target: { value: text } })
  // Submit via the form so the Enter-key plumbing and the form's
  // onSubmit handler run exactly like they do in production.
  const form = screen.getByTestId('answer-input-form') as HTMLFormElement
  fireEvent.submit(form)
}

describe('ChatPanel — answer submission flow (Story 3.4 AC#16)', () => {
  test('happy path: POST → token stream → feedback commit → input re-enabled', async () => {
    mockFetchOk()
    scriptedEvents = [
      ['feedback_token', { answer_id: 'a1', question_id: 'q1', token: 'Good ' }],
      ['feedback_token', { answer_id: 'a1', question_id: 'q1', token: 'answer.' }],
      [
        'feedback',
        {
          answer_id: 'a1',
          question_id: 'q1',
          text: 'Good answer.',
          score: null,
          gaps: [],
        },
      ],
      ['done', { question_number: 1, answer_id: 'a1' }],
    ]

    render(<ChatPanel session={makeSession()} />)
    seedPendingQuestion()

    submitAnswer('Because of caching')

    // Fetch was called with the right URL + body shape.
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled()
    })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/answers')
    expect(init.method).toBe('POST')
    const body = JSON.parse(init.body as string)
    expect(body).toEqual({ question_number: 1, text: 'Because of caching' })

    // Wait for the stream to finish. Input must re-enable.
    await waitFor(() => {
      expect(useSessionStore.getState().answerInputDisabled).toBe(false)
    })

    // Committed ai_feedback message landed.
    const committed = useSessionStore
      .getState()
      .messages.find((m) => m.kind === 'ai_feedback')
    expect(committed?.text).toBe('Good answer.')
  })

  test('409 conflict (no body): falls back to "already answered" + input re-enabled', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 409,
      body: null,
      clone: () => ({
        json: async () => {
          throw new Error('no body')
        },
      }),
    } as unknown as Response)

    render(<ChatPanel session={makeSession()} />)
    seedPendingQuestion()

    submitAnswer('late')

    await waitFor(() => {
      expect(screen.getByTestId('chat-error-banner').textContent).toContain(
        'already been answered',
      )
    })
    expect(useSessionStore.getState().answerInputDisabled).toBe(false)
  })

  test('409 answer_out_of_order: shows in-order banner, NOT "already answered"', async () => {
    // Story 3.4 kick-back regression (BLOCKER #2): the previous code
    // hardcoded the "already answered" string for every 409, which
    // confused users on 2026-04-11 manual QA. The fix parses the
    // structured ``detail.error`` code from the JSON body so the two
    // 409 cases display distinct messages.
    fetchMock.mockResolvedValue({
      ok: false,
      status: 409,
      body: null,
      clone: () => ({
        json: async () => ({
          error: 'conflict',
          message: 'Answer submitted out of order',
          detail: {
            error: 'answer_out_of_order',
            question_number: 3,
            expected_number: 1,
          },
        }),
      }),
    } as unknown as Response)

    render(<ChatPanel session={makeSession()} />)
    seedPendingQuestion()

    submitAnswer('out of order')

    await waitFor(() => {
      const banner = screen.getByTestId('chat-error-banner').textContent ?? ''
      expect(banner).toContain('answer questions in order')
      // CRITICAL: must NOT collapse into the misleading
      // "already answered" string the QA report flagged.
      expect(banner).not.toContain('already been answered')
    })
    expect(useSessionStore.getState().answerInputDisabled).toBe(false)
  })

  test('409 answer_already_submitted: shows "already answered" banner', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 409,
      body: null,
      clone: () => ({
        json: async () => ({
          error: 'conflict',
          message: 'Answer already submitted for this question',
          detail: {
            error: 'answer_already_submitted',
            question_number: 1,
          },
        }),
      }),
    } as unknown as Response)

    render(<ChatPanel session={makeSession()} />)
    seedPendingQuestion()

    submitAnswer('duplicate')

    await waitFor(() => {
      expect(screen.getByTestId('chat-error-banner').textContent).toContain(
        'already been answered',
      )
    })
    expect(useSessionStore.getState().answerInputDisabled).toBe(false)
  })

  test('422 question_text_unavailable_after_restart: shows refresh banner', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 422,
      body: null,
      clone: () => ({
        json: async () => ({
          error: 'validation_error',
          message: 'Question text is no longer in memory (server restarted?)',
          detail: { error: 'question_text_unavailable_after_restart' },
        }),
      }),
    } as unknown as Response)

    render(<ChatPanel session={makeSession()} />)
    seedPendingQuestion()

    submitAnswer('expired')

    await waitFor(() => {
      const banner = screen.getByTestId('chat-error-banner').textContent ?? ''
      expect(banner.toLowerCase()).toContain('refresh')
    })
    expect(useSessionStore.getState().answerInputDisabled).toBe(false)
  })

  test('resume from progress seeds placeholders for answered cycles', () => {
    const session = makeSession({
      total_questions: 3,
      progress: [
        { number: 1, status: 'answered', topic: 'architecture' },
        { number: 2, status: 'answered', topic: 'edge_cases' },
        { number: 3, status: 'in_flight', topic: 'architecture' },
      ],
    })
    render(<ChatPanel session={session} />)

    const messages = useSessionStore.getState().messages
    // 2 answered cycles × 3 placeholder messages (question + answer + feedback).
    expect(messages).toHaveLength(6)

    // First cycle placeholders.
    expect(messages[0]?.kind).toBe('ai_question')
    expect(messages[0]?.questionNumber).toBe(1)
    expect(messages[1]?.kind).toBe('user_answer')
    expect(messages[2]?.kind).toBe('ai_feedback')

    // All placeholder timestamps derive from session.updated_at —
    // NOT a hardcoded literal (B13+E24 from code-review).
    const timestamps = new Set(messages.map((m) => m.createdAt))
    expect(timestamps.size).toBe(1)
    expect(timestamps.has(session.updated_at)).toBe(true)
  })
})
