import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'
import ConversationOutput from './ConversationOutput'
import type { StreamMessage } from './containerTypes'

// Mock shiki — avoid loading real grammars in tests
vi.mock('./shiki', () => ({
  highlighter: {
    codeToHtml: (_code: string) => '<pre><code>mock</code></pre>',
  },
  SHIKI_THEME: 'github-dark',
  SUPPORTED_LANGS: new Set(['typescript', 'javascript']),
}))

afterEach(() => {
  cleanup()
})

function makeMessage(overrides: Partial<StreamMessage> & Pick<StreamMessage, 'id'>): StreamMessage {
  return {
    timestamp: Date.now(),
    role: 'assistant',
    blocks: [{ type: 'text', text: 'Hello world' }],
    ...overrides,
  }
}

describe('ConversationOutput', () => {
  test('renders with no messages and not running', () => {
    render(<ConversationOutput messages={[]} isRunning={false} />)

    expect(screen.getByTestId('conversation-output')).toBeTruthy()
    expect(screen.getByText('// no output yet')).toBeTruthy()
  })

  test('renders assistant text messages as markdown', () => {
    const messages = [
      makeMessage({ id: 1, blocks: [{ type: 'text', text: 'Hello world' }] }),
      makeMessage({ id: 2, blocks: [{ type: 'text', text: 'Second message' }] }),
    ]
    render(<ConversationOutput messages={messages} isRunning={false} />)

    expect(screen.getByText('Hello world')).toBeTruthy()
    expect(screen.getByText('Second message')).toBeTruthy()
  })

  test('shows cursor when running', () => {
    const messages = [makeMessage({ id: 1 })]
    render(<ConversationOutput messages={messages} isRunning={true} />)

    expect(screen.getByTestId('conversation-cursor')).toBeTruthy()
  })

  test('hides cursor when not running', () => {
    const messages = [makeMessage({ id: 1 })]
    render(<ConversationOutput messages={messages} isRunning={false} />)

    expect(screen.queryByTestId('conversation-cursor')).toBeNull()
  })

  test('has accessible log role', () => {
    render(<ConversationOutput messages={[]} isRunning={false} />)

    expect(screen.getByRole('log')).toBeTruthy()
  })

  test('renders system messages as status text', () => {
    const messages: StreamMessage[] = [
      {
        id: 1,
        timestamp: Date.now(),
        role: 'system',
        blocks: [{ type: 'text', text: 'API retry (attempt 1/3)' }],
        subtype: 'api_retry',
      },
    ]
    render(<ConversationOutput messages={messages} isRunning={true} />)

    expect(screen.getByText('// API retry (attempt 1/3)')).toBeTruthy()
  })

  test('renders error result messages', () => {
    const messages: StreamMessage[] = [
      {
        id: 1,
        timestamp: Date.now(),
        role: 'result',
        blocks: [{ type: 'text', text: 'Session ended with error' }],
        isError: true,
      },
    ]
    render(<ConversationOutput messages={messages} isRunning={false} />)

    expect(screen.getByText('Session ended with error')).toBeTruthy()
  })

  test('renders user input messages', () => {
    const messages: StreamMessage[] = [
      {
        id: 1,
        timestamp: Date.now(),
        role: 'user',
        blocks: [{ type: 'text', text: 'My answer to the question' }],
      },
    ]
    render(<ConversationOutput messages={messages} isRunning={true} />)

    expect(screen.getByText('My answer to the question')).toBeTruthy()
  })
})
