/**
 * MessageBlock — renders a single StreamMessage based on its role.
 *
 * Dispatches to role-specific layouts:
 * - assistant: markdown text + collapsible tool_use/thinking blocks
 * - user: tool_result blocks (paired with tool_use) or user input echo
 * - system: small dimmed status line
 * - result: session-end metadata
 */

import { memo } from 'react'
import type { StreamMessage, ContentBlockData } from './containerTypes'
import MarkdownContent from './MarkdownContent'
import ThinkingBlock from './ThinkingBlock'
import ToolUseBlock from './ToolUseBlock'

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
  /** Tool results from subsequent user events, keyed by tool_use_id. */
  toolResults: Map<string, ContentBlockData>
}

function AssistantMessage({ blocks, toolResults }: { blocks: ContentBlockData[]; toolResults: Map<string, ContentBlockData> }) {
  return (
    <div className="py-3">
      {blocks.map((block, i) => {
        switch (block.type) {
          case 'text':
            return <MarkdownContent key={i} text={block.text ?? ''} />
          case 'thinking':
            return <ThinkingBlock key={i} text={block.text ?? ''} />
          case 'tool_use':
            return (
              <ToolUseBlock
                key={i}
                block={block}
                result={block.tool_use_id ? toolResults.get(block.tool_use_id) : undefined}
              />
            )
          default:
            return null
        }
      })}
    </div>
  )
}

function UserInputMessage({ text }: { text: string }) {
  return (
    <div
      className="py-3 px-4 my-2 rounded-lg"
      style={{ background: 'rgba(226, 160, 57, 0.06)', borderLeft: '2px solid #E2A039' }}
    >
      <span className="text-[14px] font-sans" style={{ color: '#E0E0E0' }}>
        {text}
      </span>
    </div>
  )
}

function SystemMessage({ message }: { message: StreamMessage }) {
  const text = message.blocks[0]?.text ?? ''
  return (
    <div className="py-1">
      <span
        className="text-[12px] font-mono"
        style={{ color: '#6e6e73', fontStyle: 'italic' }}
      >
        {text}
      </span>
    </div>
  )
}

function ResultMessage({ message }: { message: StreamMessage }) {
  if (message.isError) {
    return (
      <div className="py-2">
        <span className="text-[13px] font-mono" style={{ color: '#ff6961' }}>
          {message.blocks[0]?.text ?? 'Session ended with error'}
        </span>
      </div>
    )
  }

  // Success — show metadata summary
  const parts: string[] = []
  if (message.numTurns !== undefined) {
    parts.push(`${message.numTurns} turns`)
  }
  if (message.durationMs !== undefined) {
    parts.push(formatDuration(message.durationMs))
  }
  if (parts.length === 0) return null

  return (
    <div
      className="py-2 mt-2 border-t flex items-center gap-2"
      style={{ borderColor: 'rgba(255, 255, 255, 0.06)' }}
    >
      <span className="text-[12px] font-mono" style={{ color: '#6e6e73' }}>
        Session completed
      </span>
      <span className="text-[11px] font-mono" style={{ color: '#6e6e73' }}>
        {parts.join(' / ')}
      </span>
    </div>
  )
}

function MessageBlockInner({ message, toolResults }: MessageBlockProps) {
  switch (message.role) {
    case 'assistant':
      return <AssistantMessage blocks={message.blocks} toolResults={toolResults} />
    case 'user':
      // User messages with text blocks are user input (typed in the input bar)
      if (message.blocks.length > 0 && message.blocks[0].type === 'text') {
        return <UserInputMessage text={message.blocks[0].text ?? ''} />
      }
      // User messages with only tool_result blocks are handled by pairing with tool_use.
      // They don't render independently — results are shown inside ToolUseBlock.
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
