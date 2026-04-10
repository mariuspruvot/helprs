/**
 * The default (non-reduced-motion) branch renders the streaming text
 * as it arrives. This test locks that behaviour separately from the
 * reduced-motion suite so accidentally flipping the default does not
 * go unnoticed.
 */
import { cleanup, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import ChatMessage from './ChatMessage'
import type { ChatMessage as ChatMessageType } from './types'

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
  mockMatchMedia(false)
})

afterEach(() => {
  cleanup()
})

describe('ChatMessage streaming (default branch)', () => {
  test('renders partial text while isStreaming is true', () => {
    const msg: ChatMessageType = {
      id: 'q1',
      kind: 'ai_question_streaming',
      questionNumber: 1,
      total: 3,
      text: 'Hell',
      fileRefs: [],
      createdAt: '2026-04-10T00:00:00Z',
      isStreaming: true,
    }
    const { getByTestId } = render(<ChatMessage message={msg} />)
    expect(getByTestId('chat-message-body').textContent).toContain('Hell')
  })

  test('renders the AI question header with number and total', () => {
    const msg: ChatMessageType = {
      id: 'q1',
      kind: 'ai_question',
      questionNumber: 2,
      total: 5,
      text: 'Why?',
      fileRefs: [],
      createdAt: '2026-04-10T00:00:00Z',
      isStreaming: false,
    }
    const { getByTestId } = render(<ChatMessage message={msg} />)
    expect(getByTestId('chat-message').textContent).toContain('AI question 2 of 5')
  })
})
