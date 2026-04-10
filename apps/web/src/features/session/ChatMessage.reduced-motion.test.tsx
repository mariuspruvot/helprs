/**
 * UX-DR3: `prefers-reduced-motion: reduce` disables the streaming
 * render. The network layer still streams tokens (so the backend
 * side is untouched); the component simply does not paint the
 * in-flight text until `isStreaming` flips to `false`.
 */
import { cleanup, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import ChatMessage from './ChatMessage'
import type { ChatMessage as ChatMessageType } from './types'

const STREAMING: ChatMessageType = {
  id: 'q1',
  kind: 'ai_question_streaming',
  questionNumber: 1,
  total: 3,
  text: 'Why does foo?',
  fileRefs: [],
  createdAt: '2026-04-10T00:00:00Z',
  isStreaming: true,
}

const COMMITTED: ChatMessageType = {
  ...STREAMING,
  kind: 'ai_question',
  isStreaming: false,
}

function mockMatchMedia(matches: boolean) {
  window.matchMedia = vi.fn().mockImplementation(() => ({
    matches,
    media: '(prefers-reduced-motion: reduce)',
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
}

beforeEach(() => {
  mockMatchMedia(true)
})

afterEach(() => {
  cleanup()
})

describe('ChatMessage reduced motion', () => {
  test('does NOT render the streaming text body while isStreaming is true', () => {
    const { queryByTestId, getByTestId } = render(<ChatMessage message={STREAMING} />)
    // The header + sr-only still render; the body does not.
    expect(getByTestId('chat-message')).toBeTruthy()
    expect(queryByTestId('chat-message-body')).toBeNull()
  })

  test('does render the body once the message is committed', () => {
    const { getByTestId } = render(<ChatMessage message={COMMITTED} />)
    expect(getByTestId('chat-message-body').textContent).toContain('Why does foo?')
  })
})
