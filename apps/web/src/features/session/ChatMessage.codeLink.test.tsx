import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import ChatMessage, { DiffFilePathsContext } from './ChatMessage'
import { CodeLinkActionsContext, type CodeLinkActions } from './codeLinkContext'
import type { ChatMessage as ChatMessageType } from './types'

afterEach(() => {
  cleanup()
})

function feedbackMessage(text: string): ChatMessageType {
  return {
    id: 'a1',
    kind: 'ai_feedback',
    questionNumber: 1,
    total: 3,
    text,
    fileRefs: [],
    createdAt: '2026-04-11T00:00:00Z',
    isStreaming: false,
  }
}

function questionMessage(text: string): ChatMessageType {
  return {
    id: 'q1',
    kind: 'ai_question',
    questionNumber: 1,
    total: 3,
    text,
    fileRefs: [],
    createdAt: '2026-04-11T00:00:00Z',
    isStreaming: false,
  }
}

function renderWithProviders(
  message: ChatMessageType,
  options: { diffFiles?: string[]; actions?: Partial<CodeLinkActions> } = {},
) {
  const actions: CodeLinkActions = {
    scrollTo: vi.fn(),
    preview: vi.fn(),
    clearPreview: vi.fn(),
    ...options.actions,
  }
  return {
    actions,
    ...render(
      <DiffFilePathsContext.Provider value={options.diffFiles ?? []}>
        <CodeLinkActionsContext.Provider value={actions}>
          <ChatMessage message={message} />
        </CodeLinkActionsContext.Provider>
      </DiffFilePathsContext.Provider>,
    ),
  }
}

describe('ChatMessage — code link transformation in feedback', () => {
  test('inline `path:line` matching a diff file becomes a CodeLink button', () => {
    const { actions } = renderWithProviders(
      feedbackMessage('Look at `retry.ts:47` for the issue.'),
      { diffFiles: ['retry.ts'] },
    )
    const button = screen.getByTestId('code-link-retry.ts-47')
    expect(button.tagName).toBe('BUTTON')
    expect(button.getAttribute('aria-label')).toBe('Jump to retry.ts line 47')

    fireEvent.click(button)
    expect(actions.scrollTo).toHaveBeenCalledWith('retry.ts', 47)
  })

  test('hovering a CodeLink calls preview, leaving calls clearPreview', () => {
    const { actions } = renderWithProviders(
      feedbackMessage('See `retry.ts:5` for context.'),
      { diffFiles: ['retry.ts'] },
    )
    const button = screen.getByTestId('code-link-retry.ts-5')
    fireEvent.mouseEnter(button)
    expect(actions.preview).toHaveBeenCalledWith('retry.ts', 5)
    fireEvent.mouseLeave(button)
    expect(actions.clearPreview).toHaveBeenCalled()
  })

  test('inline `path:line` whose path is NOT in the diff renders as plain code', () => {
    renderWithProviders(
      feedbackMessage('Look at `unknown.ts:10` instead.'),
      { diffFiles: ['retry.ts'] },
    )
    expect(screen.queryByTestId('code-link-unknown.ts-10')).toBeNull()
  })

  test('feedback without code refs renders no buttons', () => {
    const { container } = renderWithProviders(
      feedbackMessage('Just some plain prose with no refs.'),
      { diffFiles: ['retry.ts'] },
    )
    expect(container.querySelectorAll('button').length).toBe(0)
  })

  test('question messages do NOT promote `path:line` to CodeLink', () => {
    renderWithProviders(
      questionMessage('Why does `retry.ts:5` behave that way?'),
      { diffFiles: ['retry.ts'] },
    )
    expect(screen.queryByTestId('code-link-retry.ts-5')).toBeNull()
  })

  test('user_answer messages render with bg-surface and "You answered:" sr-only prefix', () => {
    const userMsg: ChatMessageType = {
      id: 'q1::answer',
      kind: 'user_answer',
      questionNumber: 1,
      total: 3,
      text: 'Because of caching.',
      fileRefs: [],
      createdAt: '2026-04-11T00:00:00Z',
      isStreaming: false,
    }
    const { container } = renderWithProviders(userMsg)
    const article = container.querySelector('[data-testid="chat-message"]')!
    expect(article.getAttribute('data-kind')).toBe('user_answer')
    // sr-only prefix
    const srOnly = article.querySelector('.sr-only')
    expect(srOnly?.textContent).toBe('You answered:')
    // No visible header label for user answers.
    expect(article.querySelector('header')).toBeNull()
  })

  test('feedback messages render visible "AI feedback" header (FR38)', () => {
    const { container } = renderWithProviders(feedbackMessage('Some feedback.'))
    const header = container.querySelector('[data-testid="chat-message"] header')
    expect(header?.textContent).toBe('AI feedback')
  })

  test('inline code with extra whitespace inside backticks still matches', () => {
    // Story 3.4 D2 (code-review): the fixed extractText walker
    // trims the extracted text so the regex still matches when the
    // LLM emits an inline code span with incidental whitespace.
    renderWithProviders(
      feedbackMessage('Refer to `retry.ts:47`, please.'),
      { diffFiles: ['retry.ts'] },
    )
    // Found is the documented "not null" assertion pattern in this
    // file (toBeInTheDocument is not wired via jest-dom here).
    expect(screen.queryByTestId('code-link-retry.ts-47')).not.toBeNull()
  })
})
