/**
 * Progress indicator in SessionHeader — Story 3.3 wiring.
 *
 * Asserts the string shape `"Question X of N"` where X is the count
 * of committed `ai_question` messages in the session store and N is
 * `session.total_questions`. The `aria-live="polite"` wrapper from
 * Story 3.2 must still be present.
 */
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test } from 'vitest'

import SessionHeader from './SessionHeader'
import { useSessionStore } from './store'
import type { ChatMessage } from './types'
import { makeSession, resetStores } from './__testUtils'

function committedQuestion(id: string, number: number, total: number): ChatMessage {
  return {
    id,
    kind: 'ai_question',
    questionNumber: number,
    total,
    text: 'Why?',
    fileRefs: [],
    createdAt: '2026-04-10T00:00:00Z',
    isStreaming: false,
  }
}

beforeEach(() => {
  resetStores()
})

afterEach(() => {
  cleanup()
})

describe('SessionHeader progress indicator', () => {
  test('renders "Question 2 of 5" when two questions are committed', () => {
    useSessionStore.setState({
      messages: [
        committedQuestion('q1', 1, 5),
        committedQuestion('q2', 2, 5),
      ],
    })
    render(<SessionHeader session={makeSession({ total_questions: 5 })} />)
    const progress = screen.getByTestId('session-header-progress')
    expect(progress.textContent).toBe('Question 2 of 5')
    expect(progress.getAttribute('aria-live')).toBe('polite')
  })

  test('renders "Question 0 of 3" when no questions are committed yet', () => {
    render(<SessionHeader session={makeSession({ total_questions: 3 })} />)
    const progress = screen.getByTestId('session-header-progress')
    expect(progress.textContent).toBe('Question 0 of 3')
  })

  test('renders "Questions pending..." when total_questions is zero', () => {
    render(<SessionHeader session={makeSession({ total_questions: 0 })} />)
    const progress = screen.getByTestId('session-header-progress')
    expect(progress.textContent).toBe('Questions pending...')
  })

  test('streamingQuestion does NOT count toward committed total', () => {
    useSessionStore.setState({
      messages: [committedQuestion('q1', 1, 3)],
      streamingQuestion: {
        id: 'q2',
        kind: 'ai_question_streaming',
        questionNumber: 2,
        total: 3,
        text: 'partial...',
        fileRefs: [],
        createdAt: '2026-04-10T00:00:00Z',
        isStreaming: true,
      },
    })
    render(<SessionHeader session={makeSession({ total_questions: 3 })} />)
    expect(screen.getByTestId('session-header-progress').textContent).toBe('Question 1 of 3')
  })
})
