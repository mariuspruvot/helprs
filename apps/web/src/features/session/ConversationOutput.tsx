/**
 * ConversationOutput — renders streamed session events as a conversation.
 *
 * Replaces the old TerminalOutput with structured markdown rendering,
 * syntax-highlighted code blocks, and collapsible tool activity.
 * Preserves auto-scroll, running indicator, and accessible log role.
 */

import { useEffect, useRef } from 'react'
import type { StreamMessage } from './containerTypes'
import MessageBlock from './MessageBlock'

interface ConversationOutputProps {
  messages: StreamMessage[]
  isRunning: boolean
}

export default function ConversationOutput({ messages, isRunning }: ConversationOutputProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const shouldAutoScrollRef = useRef(true)

  function handleScroll() {
    const el = containerRef.current
    if (!el) return
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    shouldAutoScrollRef.current = distanceFromBottom < 40
  }

  useEffect(() => {
    const el = containerRef.current
    if (el && shouldAutoScrollRef.current) {
      el.scrollTop = el.scrollHeight
    }
  }, [messages.length])

  return (
    <div
      data-testid="conversation-output"
      className="flex flex-col h-full"
      style={{ background: '#0D0D0D' }}
    >
      {/* Conversation body */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto overflow-x-hidden px-6 py-4"
        style={{ color: '#E0E0E0' }}
        role="log"
        aria-live="polite"
        aria-label="Session output"
      >
        {messages.length === 0 && !isRunning && (
          <p className="text-text-muted text-[13px] font-sans">No output yet.</p>
        )}
        {messages.map((message) => (
          <MessageBlock key={message.id} message={message} />
        ))}
        {isRunning && messages.length > 0 && (
          <span
            data-testid="conversation-cursor"
            className="inline-block w-2 h-4 animate-pulse mt-2"
            style={{ background: '#E2A039' }}
          />
        )}
      </div>
    </div>
  )
}
