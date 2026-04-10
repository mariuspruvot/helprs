/**
 * ChatPanel tests. We mock `useSSE` at the module boundary so the tests
 * can script exact event sequences without needing a live stream. The
 * real hook has its own unit tests in `shared/hooks/useSSE.test.ts`.
 *
 * The store is the real Zustand instance — resets live in `beforeEach`
 * (store.test.ts convention). Mocking it would obscure the integration
 * between ChatPanel and the session store.
 */
import { cleanup, render, screen } from '@testing-library/react'
import { act } from 'react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import ChatPanel from './ChatPanel'
import { useSessionStore } from './store'
import { makeSession, resetStores } from './__testUtils'

// Captured on each render so tests can fire scripted events through it.
let lastSSEProps: Record<string, unknown> | null = null

vi.mock('../../shared/hooks/useSSE', () => {
  return {
    useSSE: (options: Record<string, unknown>) => {
      lastSSEProps = options
      return { status: 'open' }
    },
  }
})

beforeEach(() => {
  resetStores()
  lastSSEProps = null
})

afterEach(() => {
  cleanup()
})

describe('ChatPanel', () => {
  test('renders the waiting placeholder when there is no content', () => {
    render(<ChatPanel session={makeSession()} />)
    expect(screen.getByTestId('chat-placeholder')).toBeTruthy()
  })

  test('passes the session stream URL to useSSE with enabled=true', () => {
    const session = makeSession({ id: 'sess-42' })
    render(<ChatPanel session={session} />)
    expect(lastSSEProps).not.toBeNull()
    expect(lastSSEProps?.url).toBe('/api/v1/sessions/sess-42/stream')
    expect(lastSSEProps?.enabled).toBe(true)
  })

  test('disables SSE when session is completed', () => {
    render(<ChatPanel session={makeSession({ status: 'completed' })} />)
    expect(lastSSEProps?.enabled).toBe(false)
  })

  test('renders streaming question on token events and commits on question event', () => {
    render(<ChatPanel session={makeSession()} />)
    const onQuestionToken = lastSSEProps?.onQuestionToken as (p: {
      questionId: string
      token: string
      number: number
      total: number
    }) => void
    const onQuestion = lastSSEProps?.onQuestion as (p: {
      question_id: string
      text: string
      number: number
      total: number
      file_refs: string[]
    }) => void

    // Scripted sequence for question 1.
    act(() => {
      onQuestionToken({ questionId: 'q1', token: 'Why', number: 1, total: 3 })
      onQuestionToken({ questionId: 'q1', token: ' does', number: 1, total: 3 })
      onQuestionToken({ questionId: 'q1', token: ' foo?', number: 1, total: 3 })
    })

    // Streaming message visible.
    const streaming = screen.getAllByTestId('chat-message')
    expect(streaming.length).toBe(1)
    expect(streaming[0]?.getAttribute('data-streaming')).toBe('true')

    // Commit q1.
    act(() => {
      onQuestion({
        question_id: 'q1',
        text: 'Why does foo call bar?',
        number: 1,
        total: 3,
        file_refs: [],
      })
    })

    // After commit, exactly one NON-streaming message.
    const committed = screen.getAllByTestId('chat-message')
    expect(committed.length).toBe(1)
    expect(committed[0]?.getAttribute('data-streaming')).toBe('false')
    expect(committed[0]?.textContent).toContain('Why does foo call bar?')
  })

  test('setActiveFile is called with the first matching file_ref', () => {
    // `makeSession` uses MULTI_FILE_DIFF which has foo.ts and bar.py.
    render(<ChatPanel session={makeSession()} />)
    // Jam activeFileIndex to 0 so the effect is visible.
    useSessionStore.setState({ activeFileIndex: 0 })

    const onQuestion = lastSSEProps?.onQuestion as (p: {
      question_id: string
      text: string
      number: number
      total: number
      file_refs: string[]
    }) => void

    act(() => {
      onQuestion({
        question_id: 'q1',
        text: 'Why does bar.py return 2?',
        number: 1,
        total: 3,
        file_refs: ['bar.py'],
      })
    })

    expect(useSessionStore.getState().activeFileIndex).toBe(1)
  })

  test('does not change activeFileIndex when file_refs is empty', () => {
    render(<ChatPanel session={makeSession()} />)
    useSessionStore.setState({ activeFileIndex: 0 })

    const onQuestion = lastSSEProps?.onQuestion as (p: {
      question_id: string
      text: string
      number: number
      total: number
      file_refs: string[]
    }) => void

    act(() => {
      onQuestion({
        question_id: 'q1',
        text: 'Generic question?',
        number: 1,
        total: 3,
        file_refs: [],
      })
    })

    expect(useSessionStore.getState().activeFileIndex).toBe(0)
  })

  test('renders error banner on server-framed error', () => {
    render(<ChatPanel session={makeSession()} />)
    const onError = lastSSEProps?.onError as (err: {
      kind: 'parse' | 'network' | 'server'
      message: string
    }) => void
    act(() => {
      onError({ kind: 'server', message: 'upstream failed' })
    })
    expect(screen.getByTestId('chat-error-banner')).toBeTruthy()
  })

  test('renders the sr-only "helPRs asks:" prefix on every message', () => {
    render(<ChatPanel session={makeSession()} />)
    const onQuestion = lastSSEProps?.onQuestion as (p: {
      question_id: string
      text: string
      number: number
      total: number
      file_refs: string[]
    }) => void
    act(() => {
      onQuestion({
        question_id: 'q1',
        text: 'Body?',
        number: 1,
        total: 3,
        file_refs: [],
      })
    })
    const message = screen.getByTestId('chat-message')
    const sr = message.querySelector('.sr-only')
    expect(sr?.textContent).toBe('helPRs asks:')
  })
})
