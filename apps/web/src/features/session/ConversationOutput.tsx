/**
 * ConversationOutput — renders streamed session events as a conversation.
 *
 * Structured markdown rendering with syntax-highlighted code blocks.
 * Direction E styling: warm dark bg, amber accents, styled message blocks.
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
      className="flex flex-col h-full bg-bg"
    >
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto overflow-x-hidden px-6 py-4"
        role="log"
        aria-live="polite"
        aria-label="Session output"
      >
        {messages.length === 0 && !isRunning && (
          <p className="text-dim text-sm font-mono">// no output yet</p>
        )}
        {messages.map((message) => (
          <MessageBlock key={message.id} message={message} />
        ))}
        {isRunning && messages.length > 0 && (
          <div data-testid="conversation-cursor" className="flex items-center gap-2 mt-3 py-2">
            <div className="flex gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-accent animate-[pulse-dot_1.4s_ease-in-out_infinite]" />
              <span className="w-1.5 h-1.5 rounded-full bg-accent animate-[pulse-dot_1.4s_ease-in-out_0.2s_infinite]" />
              <span className="w-1.5 h-1.5 rounded-full bg-accent animate-[pulse-dot_1.4s_ease-in-out_0.4s_infinite]" />
            </div>
            <span className="font-mono text-[11px] text-dim">thinking...</span>
          </div>
        )}
      </div>
    </div>
  )
}
