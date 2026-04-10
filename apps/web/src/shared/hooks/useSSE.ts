/**
 * useSSE — subscribe to a Server-Sent Events endpoint with custom event
 * handlers, cookie-based auth, and exponential-backoff reconnection.
 *
 * Deliberately lives in `shared/hooks/` (not `features/session/`) because
 * Story 3.4 will reuse it for feedback streaming. The hook stays agnostic
 * about the payload shape — callers wire each event into whatever store
 * or local state they want.
 *
 * Auth: the JWT lives in an httpOnly cookie, so `withCredentials: true` on
 * the EventSource is sufficient. We never put the token in the URL.
 *
 * Reconnection: on `readyState === CLOSED`, wait `min(16000, 500 * 2^n)` ms
 * then reopen. `attempt` resets to 0 on a successful `open`.
 */

import { useEffect, useRef, useState } from 'react'

export type SSEStatus = 'idle' | 'connecting' | 'open' | 'error' | 'closed'

export interface SSEError {
  readonly kind: 'parse' | 'network' | 'server'
  readonly message: string
  /** Raw server payload when `kind === 'server'`, else undefined. */
  readonly payload?: unknown
}

export interface UseSSEOptions {
  /** Absolute or relative URL — the browser resolves relative. */
  url: string
  /** Set to false to tear down the connection without remounting. */
  enabled?: boolean
  onQuestionToken?: (payload: {
    questionId: string
    token: string
    number: number
    total: number
  }) => void
  onQuestion?: (payload: {
    question_id: string
    text: string
    number: number
    total: number
    file_refs: string[]
  }) => void
  onDone?: (payload: { sessionId: string; questionCount: number }) => void
  onError?: (err: SSEError) => void
}

const INITIAL_BACKOFF_MS = 500
const MAX_BACKOFF_MS = 16_000

export function useSSE(options: UseSSEOptions): { status: SSEStatus } {
  const {
    url,
    enabled = true,
    onQuestionToken,
    onQuestion,
    onDone,
    onError,
  } = options

  const [status, setStatus] = useState<SSEStatus>('idle')

  // Refs so handler identity churn does not tear down + recreate the
  // EventSource on every re-render. The effect depends only on `url`
  // and `enabled`.
  const onQuestionTokenRef = useRef(onQuestionToken)
  const onQuestionRef = useRef(onQuestion)
  const onDoneRef = useRef(onDone)
  const onErrorRef = useRef(onError)

  onQuestionTokenRef.current = onQuestionToken
  onQuestionRef.current = onQuestion
  onDoneRef.current = onDone
  onErrorRef.current = onError

  useEffect(() => {
    if (!enabled) {
      setStatus('idle')
      return undefined
    }

    let source: EventSource | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let attempt = 0
    let closedByCaller = false

    const safeParse = (raw: string): unknown | undefined => {
      try {
        return JSON.parse(raw)
      } catch {
        onErrorRef.current?.({
          kind: 'parse',
          message: 'Failed to parse SSE frame as JSON',
          payload: raw,
        })
        return undefined
      }
    }

    const open = () => {
      setStatus('connecting')
      try {
        source = new EventSource(url, { withCredentials: true })
      } catch (err) {
        onErrorRef.current?.({
          kind: 'network',
          message: err instanceof Error ? err.message : 'EventSource constructor failed',
        })
        setStatus('error')
        return
      }

      source.addEventListener('open', () => {
        attempt = 0
        setStatus('open')
      })

      source.addEventListener('question_token', (event: MessageEvent) => {
        const parsed = safeParse(event.data)
        if (!parsed || typeof parsed !== 'object') return
        const obj = parsed as {
          question_id?: string
          token?: string
          number?: number
          total?: number
        }
        if (
          typeof obj.question_id === 'string' &&
          typeof obj.token === 'string' &&
          typeof obj.number === 'number' &&
          typeof obj.total === 'number'
        ) {
          onQuestionTokenRef.current?.({
            questionId: obj.question_id,
            token: obj.token,
            number: obj.number,
            total: obj.total,
          })
        }
      })

      source.addEventListener('question', (event: MessageEvent) => {
        const parsed = safeParse(event.data)
        if (!parsed || typeof parsed !== 'object') return
        onQuestionRef.current?.(
          parsed as Parameters<NonNullable<UseSSEOptions['onQuestion']>>[0],
        )
      })

      source.addEventListener('done', (event: MessageEvent) => {
        const parsed = safeParse(event.data)
        if (!parsed || typeof parsed !== 'object') return
        const obj = parsed as { session_id?: string; question_count?: number }
        if (typeof obj.session_id === 'string' && typeof obj.question_count === 'number') {
          onDoneRef.current?.({
            sessionId: obj.session_id,
            questionCount: obj.question_count,
          })
        }
      })

      source.addEventListener('error', (event: Event) => {
        // Server-framed error (SSE `event: error` frame arrives as a
        // MessageEvent with `.data`).
        if ('data' in event && typeof (event as MessageEvent).data === 'string') {
          const parsed = safeParse((event as MessageEvent).data)
          onErrorRef.current?.({
            kind: 'server',
            message: 'Server-reported stream error',
            payload: parsed,
          })
        }

        // EventSource native error — connection dropped. Schedule a
        // reconnect with exponential backoff UNLESS the caller already
        // tore us down (unmount / enabled=false toggle).
        if (source && source.readyState === EventSource.CLOSED) {
          setStatus('closed')
          if (!closedByCaller) {
            const delay = Math.min(MAX_BACKOFF_MS, INITIAL_BACKOFF_MS * 2 ** attempt)
            attempt += 1
            reconnectTimer = setTimeout(open, delay)
          }
        } else {
          setStatus('error')
        }
      })
    }

    open()

    return () => {
      closedByCaller = true
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
      }
      if (source) {
        source.close()
      }
      setStatus('closed')
    }
  }, [url, enabled])

  return { status }
}
