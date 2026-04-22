/**
 * MessageBlock — renders a single StreamMessage based on its role.
 *
 * Direction E styles:
 * - assistant: card bg + 3px amber left border
 * - user: cardHi bg + ruleStr border
 * - system: // comment ornament
 * - result: session-end metadata
 */

import { memo } from 'react'
import type { StreamMessage } from './containerTypes'
import MarkdownContent from './MarkdownContent'

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  const seconds = Math.round(ms / 1000)
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const remaining = seconds % 60
  return `${minutes}m ${remaining}s`
}

interface MessageBlockProps {
  message: StreamMessage
}

function AssistantMessage({ message }: { message: StreamMessage }) {
  const textBlocks = message.blocks.filter((b) => b.type === 'text')
  if (textBlocks.length === 0) return null

  return (
    <div className="py-3 px-4 my-2 bg-card border-l-[3px] border-l-accent rounded-r-[8px]">
      {textBlocks.map((block, i) => (
        <MarkdownContent key={i} text={block.text ?? ''} />
      ))}
    </div>
  )
}

function UserInputMessage({ text }: { text: string }) {
  return (
    <div className="py-3 px-4 my-2 bg-card-hi border border-rule-str rounded-[8px]">
      <span className="text-sm font-sans text-ink">{text}</span>
    </div>
  )
}

function SystemMessage({ message }: { message: StreamMessage }) {
  const text = message.blocks[0]?.text ?? ''
  return (
    <div className="py-1">
      <span className="text-xs font-mono text-dim">
        // {text}
      </span>
    </div>
  )
}

function ResultMessage({ message }: { message: StreamMessage }) {
  if (message.isError) {
    return (
      <div className="py-2">
        <span className="text-sm font-mono text-danger">
          {message.blocks[0]?.text ?? 'Session ended with error'}
        </span>
      </div>
    )
  }

  const parts: string[] = []
  if (message.numTurns !== undefined) {
    parts.push(`${message.numTurns} turns`)
  }
  if (message.durationMs !== undefined) {
    parts.push(formatDuration(message.durationMs))
  }
  if (parts.length === 0) return null

  return (
    <div className="py-2 mt-2 border-t border-rule flex items-center gap-2">
      <span className="text-xs font-mono text-dim">// session completed</span>
      <span className="text-[11px] font-mono text-dim2">{parts.join(' {"\u00b7"} ')}</span>
    </div>
  )
}

function MessageBlockInner({ message }: MessageBlockProps) {
  switch (message.role) {
    case 'assistant':
      return <AssistantMessage message={message} />
    case 'user':
      if (message.blocks.length > 0 && message.blocks[0].type === 'text') {
        return <UserInputMessage text={message.blocks[0].text ?? ''} />
      }
      return null
    case 'system':
      return <SystemMessage message={message} />
    case 'result':
      return <ResultMessage message={message} />
    default:
      return null
  }
}

const MessageBlock = memo(MessageBlockInner)
export default MessageBlock
