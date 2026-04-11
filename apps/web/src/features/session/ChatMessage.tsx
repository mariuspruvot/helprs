import { createContext, useContext, type ComponentPropsWithoutRef, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { useReducedMotion } from '../../shared/hooks/useReducedMotion'
import CodeLink from './CodeLink'
import type { ChatMessage as ChatMessageType } from './types'

interface ChatMessageProps {
  message: ChatMessageType
}

/**
 * Story 3.4: list of file paths in the current diff. ChatMessage
 * consumes this from `ChatPanel` via context (provided around the
 * messages.map call) so the inline code-link transformation in
 * feedback bodies can validate that a `path:line` substring actually
 * matches a real file in the diff before promoting it to a CodeLink
 * button. Drilled-as-a-prop would clutter every render call.
 *
 * Story 3.4 D2 (code-review): the frontend is the sole source of
 * truth for code-link detection. The backend's ``extract_code_refs``
 * was deleted; ChatMessage walks the rendered inline-code nodes and
 * matches against this context.
 */
export const DiffFilePathsContext = createContext<readonly string[]>([])

const CODE_REF_RE = /^([\w./-]+):(\d+)$/

/**
 * Recursively walk a react-markdown ``children`` value and concatenate
 * its text content. react-markdown ≥10 may pass nested React nodes
 * inside inline-code (e.g. `` `*retry.ts*:47` `` renders as
 * ``[<em>retry.ts</em>, ':47']``); the previous naive
 * ``Array.isArray(children) ? children.join('') : children`` would
 * collapse to ``"[object Object]:47"`` and drop the intended ref.
 */
function extractText(node: ReactNode): string {
  if (node == null || typeof node === 'boolean') return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(extractText).join('')
  if (typeof node === 'object' && 'props' in node) {
    const maybeChildren = (node as { props?: { children?: ReactNode } }).props?.children
    return extractText(maybeChildren)
  }
  return ''
}

/**
 * Renders one chat-panel message — Socratic question, user answer, or
 * AI feedback. Story 3.3 shipped only the question kinds; Story 3.4
 * adds `user_answer`, `ai_feedback`, and `ai_feedback_streaming`.
 *
 * UX-DR18 — screen reader-only prefix per kind so voice-over users
 * know which actor is speaking. FR38 — visible header label on AI
 * messages flagging AI content (dark pattern avoidance).
 *
 * UX-DR3 — when `prefers-reduced-motion: reduce` is set, the
 * streaming render is suppressed entirely. The caller still pipes
 * tokens into the store (the network traffic is unchanged), but
 * this component renders nothing until `isStreaming` flips to
 * `false` at commit time.
 */
export default function ChatMessage({ message }: ChatMessageProps) {
  const reduced = useReducedMotion()
  const diffFilePaths = useContext(DiffFilePathsContext)

  const shouldHideForReducedMotion = reduced && message.isStreaming
  const body = shouldHideForReducedMotion ? '' : message.text

  // ----- Kind-specific styling + headers ---------------------------
  const isUserAnswer = message.kind === 'user_answer'
  const isFeedback =
    message.kind === 'ai_feedback' || message.kind === 'ai_feedback_streaming'

  let backgroundColor = '#201d1d'
  let srOnlyPrefix = 'helPRs asks:'
  let visibleHeader: string | null = `AI question ${message.questionNumber} of ${message.total}`

  if (isUserAnswer) {
    backgroundColor = '#302c2c'
    srOnlyPrefix = 'You answered:'
    visibleHeader = null // no visible label for user answers
  } else if (isFeedback) {
    backgroundColor = '#201d1d'
    srOnlyPrefix = 'Feedback:'
    visibleHeader = 'AI feedback'
  }

  // ----- Markdown component overrides ------------------------------
  // Story 3.4: feedback messages get a custom `<code>` renderer that
  // promotes inline `path:line` substrings to <CodeLink> buttons.
  // Question and user_answer messages render <code> as-is — questions
  // could mention `path:line` but the ergonomics are clearer when
  // links only appear in feedback.
  const markdownComponents: ComponentPropsWithoutRef<typeof ReactMarkdown>['components'] = isFeedback
    ? {
        code: (props) => {
          const { children } = props as {
            children?: React.ReactNode
            inline?: boolean
            className?: string
          }
          // react-markdown 10 dropped the `inline` prop — distinguish
          // inline (no language class) from fenced (`language-xxx`).
          const className = (props as { className?: string }).className ?? ''
          const isFenced = className.startsWith('language-')
          if (isFenced) {
            return <code className={className}>{children}</code>
          }
          const text = extractText(children).trim()
          const match = text.match(CODE_REF_RE)
          if (match && diffFilePaths.includes(match[1]!)) {
            return <CodeLink file={match[1]!} line={Number(match[2]!)} />
          }
          return <code>{text}</code>
        },
      }
    : undefined

  return (
    <article
      data-testid="chat-message"
      data-kind={message.kind}
      data-streaming={message.isStreaming}
      data-question-number={message.questionNumber}
      className="w-full text-[15px] leading-[1.6] text-text-primary"
      style={{
        backgroundColor,
        padding: 16,
        borderRadius: 8,
        marginBottom: 16,
      }}
    >
      {/* Screen-reader-only prefix — never visible visually. */}
      <span className="sr-only">{srOnlyPrefix}</span>
      {visibleHeader !== null && (
        <header
          className="text-[12px] uppercase text-text-muted"
          style={{ marginBottom: 8, letterSpacing: '0.05em' }}
        >
          {visibleHeader}
        </header>
      )}
      {body && (
        <div data-testid="chat-message-body" className="prose prose-invert max-w-none">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
            {body}
          </ReactMarkdown>
        </div>
      )}
    </article>
  )
}
