import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { useReducedMotion } from '../../shared/hooks/useReducedMotion'
import type { ChatMessage as ChatMessageType } from './types'

interface ChatMessageProps {
  message: ChatMessageType
}

/**
 * Renders one Socratic question in the chat panel.
 *
 * UX-DR18 — screen reader-only prefix `"helPRs asks:"` so voice-over
 * users know an AI-authored turn is starting. FR38 — visible
 * `"AI question X of N"` label flags AI content (dark pattern
 * avoidance).
 *
 * UX-DR3 — when `prefers-reduced-motion: reduce` is set, the
 * streaming render is suppressed entirely. The caller still pipes
 * tokens into the store (the network traffic is unchanged), but
 * this component renders nothing until `isStreaming` flips to
 * `false` at commit time. That way the user sees one complete
 * question rather than a running animation.
 */
export default function ChatMessage({ message }: ChatMessageProps) {
  const reduced = useReducedMotion()

  const shouldHideForReducedMotion = reduced && message.isStreaming
  const body = shouldHideForReducedMotion ? '' : message.text

  return (
    <article
      data-testid="chat-message"
      data-streaming={message.isStreaming}
      data-question-number={message.questionNumber}
      className="w-full text-[15px] leading-[1.6] text-text-primary"
      style={{
        backgroundColor: '#201d1d',
        padding: 16,
        borderRadius: 8,
        marginBottom: 16,
      }}
    >
      {/* Screen-reader-only prefix — never visible visually. */}
      <span className="sr-only">helPRs asks:</span>
      <header
        className="text-[12px] uppercase text-text-muted"
        style={{ marginBottom: 8, letterSpacing: '0.05em' }}
      >
        AI question {message.questionNumber} of {message.total}
      </header>
      {body && (
        <div data-testid="chat-message-body" className="prose prose-invert max-w-none">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{body}</ReactMarkdown>
        </div>
      )}
    </article>
  )
}
