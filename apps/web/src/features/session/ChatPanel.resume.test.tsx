/**
 * Story 3.4 v1.3.0 — BLOCKER #3 regression test.
 *
 * Second manual QA pass (2026-04-11) surfaced a race in the seeding
 * `useEffect` of ChatPanel: on page reload of a session with one or
 * more answered questions, the SSE `question` frame for the in-flight
 * Q_next sometimes commits to `messages` BEFORE the seeding effect
 * runs. The pre-v1.3.0 bail condition was `messages.length > 0`, which
 * treated that streaming Q_next as "already seeded" and silently
 * skipped the resume placeholders for the completed Q1/A1/F1 cycle —
 * losing the user's visual context of completed history.
 *
 * The fix (v1.3.0):
 *   (a) Bail condition tightened to
 *       `messages.some(m => m.id.startsWith('resume-q-'))` — it now
 *       only skips when a real resume placeholder exists.
 *   (b) Placeholders are PREPENDED (not appended) so a racing Q_next
 *       that already lives in the store stays visually AFTER the
 *       resume history.
 *
 * These tests reproduce the race by pre-seeding the store with a
 * committed Q2 BEFORE rendering ChatPanel with a session whose
 * `progress` contains an answered Q1 — and assert that:
 *   1. Both the resume-q-1/resume-q-1::answer/resume-f-1 placeholders
 *      AND the streaming Q2 coexist in `messages`.
 *   2. Placeholders come first in insertion order.
 *   3. SessionHeader's "completed cycles" count reads 1 (not 0).
 */
import { cleanup, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { useAuthStore } from '../auth/store'
import ChatPanel from './ChatPanel'
import SessionHeader from './SessionHeader'
import { useSessionStore } from './store'
import { makeSession, resetStores } from './__testUtils'
import type { ChatMessage } from './types'

// Mock useSSE so GET-side streaming is a no-op — we pre-seed the
// store directly to simulate the race (a `question` frame having
// committed to the store before the seeding effect ran).
vi.mock('../../shared/hooks/useSSE', () => ({
  useSSE: () => ({ status: 'open' }),
}))

// parseSSE is not exercised by these tests but the module is imported
// by ChatPanel, so a no-op mock keeps the test from touching a real
// fetch reader.
vi.mock('../../shared/hooks/parseSSE', () => ({
  consumeSSEStream: async () => {
    /* no-op */
  },
}))

beforeEach(() => {
  resetStores()
  useAuthStore.setState({ accessToken: 'jwt-test', isAuthenticated: true })
})

afterEach(() => {
  cleanup()
})

describe('ChatPanel resume seeding vs racing SSE Q_next (BLOCKER #3)', () => {
  test('seeds resume placeholders when store already contains a streaming Q_next', () => {
    // Simulate SSE first-token arriving BEFORE the seeding effect runs.
    // appendQuestionToken pushes to streamingQuestion; the `question`
    // frame then commits it to messages[]. We skip straight to the
    // committed state since that's the problematic race scenario.
    const racingQ2: ChatMessage = {
      id: 'q2-real',
      kind: 'ai_question',
      questionNumber: 2,
      total: 3,
      text: 'What happens if the cache expires mid-request?',
      fileRefs: [],
      createdAt: '2026-04-11T16:10:00.000Z',
      isStreaming: false,
    }
    useSessionStore.setState({ messages: [racingQ2] })

    const session = makeSession({
      total_questions: 3,
      progress: [
        { number: 1, status: 'answered', topic: 'architecture' },
        { number: 2, status: 'in_flight', topic: 'architecture' },
      ],
    })

    render(<ChatPanel session={session} />)

    const messages = useSessionStore.getState().messages
    // 3 resume placeholders for Q1 + the pre-existing Q2 = 4.
    expect(messages).toHaveLength(4)

    // The resume placeholders exist AND carry the expected ids.
    const ids = messages.map((m) => m.id)
    expect(ids).toContain('resume-q-1')
    expect(ids).toContain('resume-q-1::answer')
    expect(ids).toContain('resume-f-1')
    expect(ids).toContain('q2-real')

    // Ordering: placeholders come BEFORE the racing Q_next so the
    // chat panel renders completed cycles above in-flight streaming.
    expect(messages[0]?.id).toBe('resume-q-1')
    expect(messages[1]?.id).toBe('resume-q-1::answer')
    expect(messages[2]?.id).toBe('resume-f-1')
    expect(messages[3]?.id).toBe('q2-real')
  })

  test('SessionHeader reads 1 completed cycle after resume seeding', () => {
    // Same pre-seed → ensures the ai_feedback placeholder seeded by
    // ChatPanel drives SessionHeader's "completed cycles" count.
    const racingQ2: ChatMessage = {
      id: 'q2-real',
      kind: 'ai_question',
      questionNumber: 2,
      total: 3,
      text: 'What happens if the cache expires mid-request?',
      fileRefs: [],
      createdAt: '2026-04-11T16:10:00.000Z',
      isStreaming: false,
    }
    useSessionStore.setState({ messages: [racingQ2] })

    const session = makeSession({
      total_questions: 3,
      progress: [
        { number: 1, status: 'answered', topic: 'architecture' },
        { number: 2, status: 'in_flight', topic: 'architecture' },
      ],
    })

    const { getByTestId } = render(
      <>
        <SessionHeader session={session} />
        <ChatPanel session={session} />
      </>,
    )

    const header = getByTestId('session-header').textContent ?? ''
    expect(header).toContain('Question 1 of 3')
  })

  test('does NOT re-seed when resume placeholders already exist (bail works)', () => {
    // Pre-seed the store with an existing resume placeholder as if a
    // previous ChatPanel mount had already seeded it. Re-rendering
    // must NOT duplicate the placeholders.
    const alreadySeeded: ChatMessage[] = [
      {
        id: 'resume-q-1',
        kind: 'ai_question',
        questionNumber: 1,
        total: 3,
        text: '_(question text not retained)_',
        fileRefs: [],
        createdAt: '2026-04-10T00:00:00Z',
        isStreaming: false,
      },
      {
        id: 'resume-q-1::answer',
        kind: 'user_answer',
        questionNumber: 1,
        total: 3,
        text: '_(answer text not retained)_',
        fileRefs: [],
        createdAt: '2026-04-10T00:00:00Z',
        isStreaming: false,
      },
      {
        id: 'resume-f-1',
        kind: 'ai_feedback',
        questionNumber: 1,
        total: 3,
        text: '_(feedback text not retained)_',
        fileRefs: [],
        createdAt: '2026-04-10T00:00:00Z',
        isStreaming: false,
      },
    ]
    useSessionStore.setState({ messages: alreadySeeded })

    const session = makeSession({
      total_questions: 3,
      progress: [
        { number: 1, status: 'answered', topic: 'architecture' },
        { number: 2, status: 'in_flight', topic: 'architecture' },
      ],
    })

    render(<ChatPanel session={session} />)

    // No duplication: still 3 messages, same ids.
    const messages = useSessionStore.getState().messages
    expect(messages).toHaveLength(3)
    expect(messages.map((m) => m.id)).toEqual(['resume-q-1', 'resume-q-1::answer', 'resume-f-1'])

    // v1.3.0 review P4: length + ids alone cannot distinguish "bail
    // worked" from "re-seeded with identical structure". Assert that
    // the original ``createdAt`` stamps are preserved — the seeding
    // effect, if it re-ran, would stamp fresh placeholders with the
    // session's current updated_at rather than the pre-seeded
    // '2026-04-10T00:00:00Z'.
    expect(messages[0]?.createdAt).toBe('2026-04-10T00:00:00Z')
    expect(messages[1]?.createdAt).toBe('2026-04-10T00:00:00Z')
    expect(messages[2]?.createdAt).toBe('2026-04-10T00:00:00Z')
  })
})
