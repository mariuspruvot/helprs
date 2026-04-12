/**
 * Progress indicator in SessionHeader.
 *
 * Story 3.4 changed the semantics: the counter now reflects COMPLETED
 * CYCLES (ai_feedback messages) rather than just questions, because a
 * cycle is "complete" only once feedback has shipped. A question that
 * has been asked but not yet answered does NOT advance the counter.
 *
 * Asserts the string shape `"Question X of N"` where X is the count
 * of `ai_feedback` messages in the session store and N is
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

function userAnswer(questionId: string, number: number, total: number): ChatMessage {
  return {
    id: `${questionId}::answer`,
    kind: 'user_answer',
    questionNumber: number,
    total,
    text: 'Because.',
    fileRefs: [],
    createdAt: '2026-04-10T00:00:00Z',
    isStreaming: false,
  }
}

function feedback(answerId: string, number: number, total: number): ChatMessage {
  return {
    id: answerId,
    kind: 'ai_feedback',
    questionNumber: number,
    total,
    text: 'Good.',
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
  test('renders "Question 2 of 5" when two FEEDBACK cycles are completed', () => {
    useSessionStore.setState({
      messages: [
        committedQuestion('q1', 1, 5),
        userAnswer('q1', 1, 5),
        feedback('a1', 1, 5),
        committedQuestion('q2', 2, 5),
        userAnswer('q2', 2, 5),
        feedback('a2', 2, 5),
      ],
    })
    render(<SessionHeader session={makeSession({ total_questions: 5 })} />)
    const progress = screen.getByTestId('session-header-progress')
    expect(progress.textContent).toBe('Question 2 of 5')
    expect(progress.getAttribute('aria-live')).toBe('polite')
  })

  test('Story 3.4: a question without feedback does NOT advance the counter', () => {
    useSessionStore.setState({
      messages: [
        committedQuestion('q1', 1, 3),
        userAnswer('q1', 1, 3),
        feedback('a1', 1, 3),
        // Q2 has been asked but not answered yet — counter stays at 1.
        committedQuestion('q2', 2, 3),
      ],
    })
    render(<SessionHeader session={makeSession({ total_questions: 3 })} />)
    expect(screen.getByTestId('session-header-progress').textContent).toBe('Question 1 of 3')
  })

  test('renders "Question 0 of 3" when no questions have been answered yet', () => {
    render(<SessionHeader session={makeSession({ total_questions: 3 })} />)
    const progress = screen.getByTestId('session-header-progress')
    expect(progress.textContent).toBe('Question 0 of 3')
  })

  test('renders "Questions pending..." when total_questions is zero', () => {
    render(<SessionHeader session={makeSession({ total_questions: 0 })} />)
    const progress = screen.getByTestId('session-header-progress')
    expect(progress.textContent).toBe('Questions pending...')
  })

  test('Story 3.5: renders "Question 0 of 8" for a large-tier session', () => {
    // Story 3.5 introduces the 4/6/8 tier counts — verify the header
    // layout handles the new large-tier value without hardcoding 5.
    render(<SessionHeader session={makeSession({ total_questions: 8 })} />)
    expect(screen.getByTestId('session-header-progress').textContent).toBe('Question 0 of 8')
  })

  test('Story 3.5: renders "Question 4 of 8" after four completed cycles (large tier)', () => {
    useSessionStore.setState({
      messages: [
        committedQuestion('q1', 1, 8),
        userAnswer('q1', 1, 8),
        feedback('a1', 1, 8),
        committedQuestion('q2', 2, 8),
        userAnswer('q2', 2, 8),
        feedback('a2', 2, 8),
        committedQuestion('q3', 3, 8),
        userAnswer('q3', 3, 8),
        feedback('a3', 3, 8),
        committedQuestion('q4', 4, 8),
        userAnswer('q4', 4, 8),
        feedback('a4', 4, 8),
      ],
    })
    render(<SessionHeader session={makeSession({ total_questions: 8 })} />)
    expect(screen.getByTestId('session-header-progress').textContent).toBe('Question 4 of 8')
  })

  test('streamingFeedback does NOT count toward completed cycles', () => {
    useSessionStore.setState({
      messages: [committedQuestion('q1', 1, 3), userAnswer('q1', 1, 3)],
      streamingFeedback: {
        id: 'a1',
        kind: 'ai_feedback_streaming',
        questionNumber: 1,
        total: 3,
        text: 'partial...',
        fileRefs: [],
        createdAt: '2026-04-10T00:00:00Z',
        isStreaming: true,
      },
    })
    render(<SessionHeader session={makeSession({ total_questions: 3 })} />)
    expect(screen.getByTestId('session-header-progress').textContent).toBe('Question 0 of 3')
  })
})
