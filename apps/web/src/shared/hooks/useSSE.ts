/**
 * useSSE — subscribe to a Server-Sent Events endpoint with custom event
 * handlers, cookie-based auth, and exponential-backoff reconnection.
 *
 * Deliberately lives in `shared/hooks/` (not `features/session/`) because
 * Story 3.4 will reuse it for feedback streaming. The hook stays agnostic
 * about the payload shape — callers wire each event into whatever store
 * or local state they want.
 *
 * Auth: `EventSource` cannot send custom headers, so the access JWT
 * is appended to the URL as a `?access_token=` query parameter by the
 * caller (see `ChatPanel.tsx`). The backend's `get_current_user`
 * accepts the token from either the `Authorization` header or this
 * query param. `withCredentials: true` is still set so any CORS+cookie
 * needs (e.g. CSRF) keep working, but auth itself is via the URL token.
 * Discovered + fixed during Story 3-3 manual QA on 2026-04-11 — the
 * earlier "JWT lives in a cookie" comment was an unverified assumption.
 *
 * Reconnection policy (P1/P2/P3 from story-3.3 review):
 *
 * - On `readyState === CLOSED` from a native error, wait
 *   `min(16000, 500 * 2^n)` ms then reopen. `attempt` resets to 0 on a
 *   successful `open`.
 * - A server-framed `event: error` frame fires `onError({kind:'server'})`
 *   and marks the stream terminal — NO reconnect. The server has already
 *   told us the stream is over.
 * - A server-framed `event: done` frame also marks the stream terminal.
 *   Otherwise the browser fires `error` with `readyState === CLOSED` as
 *   soon as the backend closes the connection after `done`, and the
 *   reconnect loop would re-invoke the whole pipeline indefinitely.
 * - On unmount / `enabled=false`, the pending reconnect timer is
 *   cleared and the scheduled callback refuses to run.
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

type HandlersRef = {
  onQuestionToken?: UseSSEOptions['onQuestionToken']
  onQuestion?: UseSSEOptions['onQuestion']
  onDone?: UseSSEOptions['onDone']
  onError?: UseSSEOptions['onError']
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

export function useSSE(options: UseSSEOptions): { status: SSEStatus } {
  const { url, enabled = true, onQuestionToken, onQuestion, onDone, onError } = options

  const [status, setStatus] = useState<SSEStatus>('idle')

  // P4: refs are updated inside an effect (not in the render body) so
  // React 18 concurrent renders that are discarded cannot leave the
  // open EventSource pointing at torn-down handler identities.
  const handlersRef = useRef<HandlersRef>({})
  useEffect(() => {
    handlersRef.current = { onQuestionToken, onQuestion, onDone, onError }
  }, [onQuestionToken, onQuestion, onDone, onError])

  useEffect(() => {
    if (!enabled) {
      setStatus('idle')
      return undefined
    }

    let source: EventSource | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let attempt = 0
    let closedByCaller = false
    // P1/P2: once the server has told us the stream is over (either via
    // ``event: done`` or ``event: error``), the hook stops reconnecting.
    // The native ``error`` event that fires immediately after the
    // backend closes the connection must be ignored.
    let terminal = false

    const safeParse = (raw: string): unknown => {
      try {
        return JSON.parse(raw)
      } catch {
        handlersRef.current.onError?.({
          kind: 'parse',
          message: 'Failed to parse SSE frame as JSON',
          payload: raw,
        })
        return undefined
      }
    }

    const scheduleReconnect = () => {
      if (closedByCaller || terminal) return
      const delay = Math.min(MAX_BACKOFF_MS, INITIAL_BACKOFF_MS * 2 ** attempt)
      attempt += 1
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null
        // P3: re-check the terminal/caller flags inside the timer
        // callback so an unmount or a late ``done`` frame that landed
        // while the timer was pending wins.
        if (closedByCaller || terminal) return
        open()
      }, delay)
    }

    const open = () => {
      // P3: close any previous EventSource before reassigning so the
      // browser releases its listeners + network resources rather than
      // accumulating zombies across reconnects.
      if (source) {
        source.close()
        source = null
      }

      setStatus('connecting')
      let next: EventSource
      try {
        next = new EventSource(url, { withCredentials: true })
      } catch (err) {
        handlersRef.current.onError?.({
          kind: 'network',
          message: err instanceof Error ? err.message : 'EventSource constructor failed',
        })
        setStatus('error')
        return
      }
      source = next

      next.addEventListener('open', () => {
        attempt = 0
        setStatus('open')
      })

      next.addEventListener('question_token', (event: MessageEvent) => {
        const parsed = safeParse(event.data)
        if (!isRecord(parsed)) return
        const { question_id, token, number, total } = parsed
        if (
          typeof question_id === 'string' &&
          typeof token === 'string' &&
          typeof number === 'number' &&
          typeof total === 'number'
        ) {
          handlersRef.current.onQuestionToken?.({
            questionId: question_id,
            token,
            number,
            total,
          })
        }
      })

      next.addEventListener('question', (event: MessageEvent) => {
        const parsed = safeParse(event.data)
        if (!isRecord(parsed)) return
        // P5: validate the payload shape before forwarding. Previously
        // this branch cast `parsed` straight to the callback type, so
        // a frame missing ``file_refs`` crashed the caller on
        // ``.length``. Now we fail soft via ``onError({kind:'server'})``
        // and keep the stream alive.
        const { question_id, text, number, total, file_refs } = parsed
        if (
          typeof question_id !== 'string' ||
          typeof text !== 'string' ||
          typeof number !== 'number' ||
          typeof total !== 'number' ||
          !Array.isArray(file_refs) ||
          !file_refs.every((ref): ref is string => typeof ref === 'string')
        ) {
          handlersRef.current.onError?.({
            kind: 'server',
            message: 'Malformed `question` frame: missing or wrong-typed fields',
            payload: parsed,
          })
          return
        }
        handlersRef.current.onQuestion?.({
          question_id,
          text,
          number,
          total,
          file_refs,
        })
      })

      next.addEventListener('done', (event: MessageEvent) => {
        const parsed = safeParse(event.data)
        if (!isRecord(parsed)) return
        const { session_id, question_count } = parsed
        if (typeof session_id === 'string' && typeof question_count === 'number') {
          // P2: mark the stream terminal BEFORE firing the callback so
          // the native ``error`` event that follows the backend's
          // connection close cannot schedule a reconnect.
          terminal = true
          if (source) {
            source.close()
            source = null
          }
          setStatus('closed')
          handlersRef.current.onDone?.({
            sessionId: session_id,
            questionCount: question_count,
          })
        }
      })

      next.addEventListener('error', (event: Event) => {
        // Distinguish a server-framed `event: error` frame (which
        // arrives as a MessageEvent carrying JSON) from a native error
        // (connection drop — no `data`).
        const isServerFramed =
          'data' in event && typeof (event as MessageEvent).data === 'string'

        if (isServerFramed) {
          const parsed = safeParse((event as MessageEvent).data)
          // P1: a server-framed error ends the stream. We notify the
          // caller and mark terminal so the subsequent native `error`
          // from the backend's connection close does NOT schedule a
          // reconnect. Reconnect storms on non-transient failures
          // (missing BYOK, schema drift) are the worst offenders here.
          terminal = true
          if (source) {
            source.close()
            source = null
          }
          setStatus('closed')
          handlersRef.current.onError?.({
            kind: 'server',
            message: 'Server-reported stream error',
            payload: parsed,
          })
          return
        }

        // Native error path — EventSource dropped the connection.
        // Reconnect unless the caller has torn us down or the server
        // already told us the stream is over.
        if (next.readyState === EventSource.CLOSED) {
          setStatus('closed')
          if (!closedByCaller && !terminal) {
            handlersRef.current.onError?.({
              kind: 'network',
              message: 'EventSource connection closed',
            })
            scheduleReconnect()
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
        reconnectTimer = null
      }
      if (source) {
        source.close()
        source = null
      }
      setStatus('closed')
    }
  }, [url, enabled])

  return { status }
}
