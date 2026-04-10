import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { useSSE, type SSEError } from '../../shared/hooks/useSSE'
import ChatMessage from './ChatMessage'
import { useSessionStore } from './store'
import type { SessionResponse } from './types'

interface ChatPanelProps {
  session: SessionResponse
}

/**
 * Parse the set of file paths in a unified diff.
 *
 * Kept inline (not imported from a shared util) because this is the
 * only consumer on the frontend — the backend has its own equivalent
 * in `infrastructure/diff_refs.py`. If a second consumer appears,
 * promote this to `shared/utils/diffFilePaths.ts`.
 */
function parseDiffFilePaths(diff: string): string[] {
  const seen = new Set<string>()
  const ordered: string[] = []
  const gitLineRegex = /^diff --git a\/(.+?) b\/(.+?)$/gm
  let match: RegExpExecArray | null
  while ((match = gitLineRegex.exec(diff)) !== null) {
    for (const path of [match[1], match[2]]) {
      if (path && path !== '/dev/null' && !seen.has(path)) {
        seen.add(path)
        ordered.push(path)
      }
    }
  }
  return ordered
}

/**
 * ChatPanel — the left panel of the split view.
 *
 * Story 3.3 replaces the Story 3.2 placeholder with a live chat
 * message list driven by Server-Sent Events. Key behaviours:
 *
 * - Opens a single SSE stream on mount (closed on unmount).
 * - Renders each committed message + the in-flight streaming message.
 * - Calls `setActiveFile` when a committed question references files.
 * - Auto-scrolls to bottom on each token append UNLESS the user has
 *   scrolled up manually (no "Jump to latest" button — that's out of
 *   scope for 3.3).
 * - Shows the "Waiting for the first question..." placeholder until
 *   either a streaming message or a committed message exists.
 * - Falls back to an inline error banner on stream errors.
 */
export default function ChatPanel({ session }: ChatPanelProps) {
  const messages = useSessionStore((s) => s.messages)
  const streamingQuestion = useSessionStore((s) => s.streamingQuestion)
  const appendQuestionToken = useSessionStore((s) => s.appendQuestionToken)
  const commitStreamingQuestion = useSessionStore((s) => s.commitStreamingQuestion)
  const setActiveFile = useSessionStore((s) => s.setActiveFile)

  const [sseError, setSseError] = useState<string | null>(null)

  const diffFilePaths = useMemo(() => parseDiffFilePaths(session.diff), [session.diff])

  const scrollContainerRef = useRef<HTMLDivElement | null>(null)
  const autoScrollRef = useRef(true)

  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current
    if (!el) return
    autoScrollRef.current = el.scrollTop >= el.scrollHeight - el.clientHeight - 50
  }, [])

  // Auto-scroll on new content if the user has not scrolled up.
  useEffect(() => {
    const el = scrollContainerRef.current
    if (!el) return
    if (autoScrollRef.current) {
      el.scrollTop = el.scrollHeight
    }
  }, [messages.length, streamingQuestion?.text])

  const handleQuestionToken = useCallback(
    (payload: { questionId: string; token: string; number: number; total: number }) => {
      appendQuestionToken(payload.questionId, payload.token, payload.number, payload.total)
    },
    [appendQuestionToken],
  )

  const handleQuestion = useCallback(
    (payload: {
      question_id: string
      text: string
      number: number
      total: number
      file_refs: string[]
    }) => {
      commitStreamingQuestion(payload)
      if (payload.file_refs.length > 0) {
        // Highlight the first referenced file that exists in the diff.
        const firstRef = payload.file_refs.find((ref) => diffFilePaths.includes(ref))
        if (firstRef) {
          const index = diffFilePaths.indexOf(firstRef)
          if (index >= 0) {
            setActiveFile(index)
          }
        }
      }
    },
    [commitStreamingQuestion, diffFilePaths, setActiveFile],
  )

  const handleError = useCallback((err: SSEError) => {
    if (err.kind === 'server') {
      setSseError('The question stream reported an error. Please retry.')
    } else if (err.kind === 'network') {
      setSseError('Connection lost. Reconnecting...')
    }
  }, [])

  const handleDone = useCallback(() => {
    setSseError(null)
  }, [])

  const sseEnabled = session.status !== 'completed'
  const sseUrl = `/api/v1/sessions/${session.id}/stream`
  useSSE({
    url: sseUrl,
    enabled: sseEnabled,
    onQuestionToken: handleQuestionToken,
    onQuestion: handleQuestion,
    onDone: handleDone,
    onError: handleError,
  })

  const hasContent = messages.length > 0 || streamingQuestion !== null

  return (
    <div
      className="h-full w-full bg-primary flex flex-col overflow-hidden"
      data-testid="chat-panel"
    >
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto flex flex-col"
      >
        <div className="max-w-[720px] w-full mx-auto px-4 py-6 flex-1 flex flex-col">
          {sseError && (
            <div
              role="alert"
              data-testid="chat-error-banner"
              className="text-[13px] text-text-secondary"
              style={{
                padding: 12,
                marginBottom: 16,
                borderRadius: 8,
                backgroundColor: 'rgba(255, 69, 58, 0.15)',
                color: '#ff453a',
              }}
            >
              {sseError}
            </div>
          )}

          {!hasContent && (
            <div className="flex-1 flex items-center justify-center">
              <p className="text-[14px] text-text-muted" data-testid="chat-placeholder">
                Waiting for the first question...
              </p>
            </div>
          )}

          {hasContent && (
            <div data-testid="chat-message-list">
              {messages.map((m) => (
                <ChatMessage key={m.id} message={m} />
              ))}
              {streamingQuestion && (
                <ChatMessage key={streamingQuestion.id} message={streamingQuestion} />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
