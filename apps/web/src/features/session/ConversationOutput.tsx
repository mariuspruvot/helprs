/**
 * ConversationOutput — renders streamed session events as a conversation.
 *
 * Replaces the old TerminalOutput with structured markdown rendering,
 * syntax-highlighted code blocks, and collapsible tool activity.
 * Preserves auto-scroll, running indicator, and accessible log role.
 */

import { useEffect, useMemo, useRef } from 'react'
import type { StreamMessage, ContentBlockData } from './containerTypes'
import MessageBlock from './MessageBlock'

interface ConversationOutputProps {
  messages: StreamMessage[]
  isRunning: boolean
}

/**
 * Build a map of tool_use_id -> tool_result block by scanning user messages.
 * This allows ToolUseBlock to display its paired result inline.
 */
function buildToolResultsMap(messages: StreamMessage[]): Map<string, ContentBlockData> {
  const map = new Map<string, ContentBlockData>()
  for (const msg of messages) {
    if (msg.role !== 'user') continue
    for (const block of msg.blocks) {
      if (block.type === 'tool_result' && block.tool_use_id) {
        map.set(block.tool_use_id, block)
      }
    }
  }
  return map
}

export default function ConversationOutput({ messages, isRunning }: ConversationOutputProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const shouldAutoScrollRef = useRef(true)

  const toolResults = useMemo(() => buildToolResultsMap(messages), [messages])

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
      {/* Header bar */}
      <div
        className="flex items-center gap-2 px-4 py-2 border-b"
        style={{
          borderColor: 'rgba(255, 255, 255, 0.06)',
          background: '#111111',
        }}
      >
        <div className="flex gap-1.5">
          <span className="w-3 h-3 rounded-full" style={{ background: '#FF5F57' }} />
          <span className="w-3 h-3 rounded-full" style={{ background: '#FEBC2E' }} />
          <span className="w-3 h-3 rounded-full" style={{ background: '#28C840' }} />
        </div>
        <span
          className="text-[12px] font-mono ml-2"
          style={{ color: 'rgba(255, 255, 255, 0.4)' }}
        >
          helPRs session
        </span>
        {isRunning && (
          <span
            data-testid="conversation-running-indicator"
            className="ml-auto text-[11px] font-mono flex items-center gap-1.5"
            style={{ color: '#E2A039' }}
          >
            <span className="inline-block w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: '#E2A039' }} />
            running
          </span>
        )}
      </div>

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
          <MessageBlock key={message.id} message={message} toolResults={toolResults} />
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
