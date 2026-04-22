/**
 * ContainerSession — manages the lifecycle of a container skill session.
 *
 * 1. POSTs to create a session
 * 2. Connects to SSE stream for real-time output
 * 3. Displays output as a split layout: transcript left, rail right
 * 4. Provides stop/back controls and post-session scorecard
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useAuthStore } from '../auth/store'
import { Button, Chip } from '../../shared/components'
import {
  buildStreamUrl,
  createContainerSession,
  fetchScorecard,
  getContainerSession,
  getSessionEvents,
  sendMessage,
  stopContainerSession,
} from './containerApi'
import ConversationOutput from './ConversationOutput'
import SessionRail from './SessionRail'
import type { ScorecardResponse } from './containerApi'
import {
  extractScorecardFromText,
  parseStoredMessage,
  parseStreamMessage,
} from './containerTypes'
import type {
  ContainerSessionResponse,
  ContainerStatus,
  StreamMessage,
} from './containerTypes'

interface ContainerSessionProps {
  installationId: string
  repoFullName: string
  prNumber: number
  skillName: string
  onBack: () => void
  existingSessionId?: string
}

export default function ContainerSession({
  installationId,
  repoFullName,
  prNumber,
  skillName,
  onBack,
  existingSessionId,
}: ContainerSessionProps) {
  const [session, setSession] = useState<ContainerSessionResponse | null>(null)
  const [messages, setMessages] = useState<StreamMessage[]>([])
  const [status, setStatus] = useState<ContainerStatus>('pending')
  const [error, setError] = useState<string | null>(null)
  const [stopping, setStopping] = useState(false)
  const [userInput, setUserInput] = useState('')
  const [sending, setSending] = useState(false)
  const [isThinking, setIsThinking] = useState(true)
  const [scorecard, setScorecard] = useState<ScorecardResponse | null>(null)

  // Question tracking for progress rail
  const [questionCount, setQuestionCount] = useState(0)
  const [currentQuestion, setCurrentQuestion] = useState(0)

  const msgIdRef = useRef(0)
  const sseOffsetRef = useRef(0)
  const reconnectCountRef = useRef(0)
  const eventSourceRef = useRef<EventSource | null>(null)
  const mountedRef = useRef(true)
  const inputRef = useRef<HTMLInputElement>(null)

  const MAX_RECONNECTS = 5
  const RECONNECT_BASE_DELAY_MS = 2000

  const appendMessage = useCallback((partial: Omit<StreamMessage, 'id' | 'timestamp'>) => {
    if (!mountedRef.current) return
    msgIdRef.current += 1
    const msg: StreamMessage = {
      ...partial,
      id: msgIdRef.current,
      timestamp: Date.now(),
    }
    setMessages((prev) => [...prev, msg])

    // Track question progress from assistant text
    if (partial.role === 'assistant') {
      for (const block of partial.blocks) {
        if (block.type === 'text' && block.text) {
          // Detect question patterns like "Q 1 / 3", "Question 1/3", "## Question 1"
          const qMatch = block.text.match(/(?:Q(?:uestion)?\s*(\d+)\s*[/|of]\s*(\d+))|(?:##\s*Question\s*(\d+))/i)
          if (qMatch) {
            const qNum = parseInt(qMatch[1] ?? qMatch[3] ?? '0', 10)
            const qTotal = parseInt(qMatch[2] ?? '0', 10)
            if (qTotal > 0) setQuestionCount(qTotal)
            if (qNum > 0) setCurrentQuestion(qNum)
          }
        }
      }
    }
  }, [])

  const appendStatus = useCallback((text: string, subtype?: string) => {
    appendMessage({
      role: 'system',
      blocks: [{ type: 'text', text }],
      subtype,
    })
  }, [appendMessage])

  const appendError = useCallback((text: string) => {
    appendMessage({
      role: 'result',
      blocks: [{ type: 'text', text }],
      isError: true,
    })
  }, [appendMessage])

  // Refresh session data (to get completed_at for the timer) and scorecard
  const refreshSessionData = useCallback(async (sessionId: string) => {
    try {
      const [fresh, sc] = await Promise.all([
        getContainerSession(sessionId).catch(() => null),
        fetchScorecard(sessionId).catch(() => null),
      ])
      if (fresh) setSession(fresh)
      if (sc) setScorecard(sc)
    } catch {
      // best-effort
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    const abortController = new AbortController()
    msgIdRef.current = 0
    sseOffsetRef.current = 0
    reconnectCountRef.current = 0
    setMessages([])

    async function loadStoredEvents(sessionId: string) {
      try {
        const resp = await getSessionEvents(sessionId)
        for (const evt of resp.events) {
          // Extract scorecard from stored assistant events
          if (evt.data.type === 'assistant') {
            const content = (evt.data.message as { content?: Array<{ type: string; text?: string }> })?.content
            if (content) {
              for (const block of content) {
                if (block.type === 'text' && block.text) {
                  const sc = extractScorecardFromText(block.text)
                  if (sc) setScorecard(sc as unknown as ScorecardResponse)
                }
              }
            }
          }
          const parsed = parseStoredMessage(evt.data)
          if (parsed) {
            appendMessage(parsed)
          }
        }
      } catch {
        appendError('Failed to load session history.')
      }
    }

    async function init() {
      try {
        if (existingSessionId) {
          const existing = await getContainerSession(existingSessionId)
          if (abortController.signal.aborted) return
          setSession(existing)
          setStatus(existing.status)

          const isTerminalStatus = ['completed', 'failed', 'timeout', 'stopped'].includes(existing.status)
          if (isTerminalStatus) {
            await loadStoredEvents(existing.id)
            await refreshSessionData(existing.id)
          } else if (existing.status === 'running') {
            connectStream(existing.id)
          }
          return
        }

        setStatus('starting')
        appendStatus(`Starting ${skillName} for ${repoFullName}#${prNumber}...`)

        const created = await createContainerSession(
          {
            installation_id: installationId,
            pr_number: prNumber,
            repo_full_name: repoFullName,
            skill_name: skillName,
          },
          abortController.signal,
        )

        if (abortController.signal.aborted) return

        setSession(created)
        setStatus(created.status)

        if (created.status === 'running' || created.status === 'starting') {
          connectStream(created.id)
        } else if (created.status === 'failed') {
          setError('Container failed to start')
          appendError('Container failed to start.')
        }
      } catch (err) {
        if (abortController.signal.aborted) return
        const msg = err instanceof Error ? err.message : 'Unknown error'
        setError(msg)
        setStatus('failed')
        appendError(msg)
      }
    }

    async function pollSessionStatus(sessionId: string) {
      reconnectCountRef.current += 1
      if (reconnectCountRef.current > MAX_RECONNECTS) {
        setStatus('failed')
        setError('Lost connection to session')
        appendError('Lost connection after multiple retries.')
        return
      }

      const delay = RECONNECT_BASE_DELAY_MS * Math.pow(2, reconnectCountRef.current - 1)
      await new Promise((r) => setTimeout(r, delay))
      if (!mountedRef.current) return

      try {
        const fresh = await getContainerSession(sessionId)
        if (!mountedRef.current) return
        setStatus(fresh.status)
        if (fresh.status === 'completed') {
          appendStatus('Session completed.')
          await loadStoredEvents(sessionId)
          await refreshSessionData(sessionId)
        } else if (fresh.status === 'failed') {
          setError('Container failed')
          appendError('Container failed.')
          await loadStoredEvents(sessionId)
        } else if (fresh.status === 'running') {
          connectStream(sessionId)
        }
      } catch {
        if (!mountedRef.current) return
        setStatus('failed')
        setError('Lost connection to session')
        appendError('Lost connection to session.')
      }
    }

    function connectStream(sessionId: string) {
      const accessToken = useAuthStore.getState().accessToken
      if (!accessToken) {
        setError('Not authenticated')
        return
      }

      const url = buildStreamUrl(sessionId, accessToken, sseOffsetRef.current)
      const source = new EventSource(url, { withCredentials: true })
      eventSourceRef.current = source

      source.addEventListener('open', () => {
        if (!mountedRef.current) return
        setStatus('running')
        reconnectCountRef.current = 0
      })

      source.onmessage = (event: MessageEvent) => {
        if (!mountedRef.current) return
        if (event.lastEventId) {
          sseOffsetRef.current = parseInt(event.lastEventId, 10) || sseOffsetRef.current
        }

        try {
          const raw = JSON.parse(event.data as string) as { type?: string }
          if (raw.type === 'assistant') setIsThinking(true)
          else if (raw.type === 'result') setIsThinking(false)
        } catch {
          // ignore
        }

        // Check for scorecard in raw assistant text before it gets stripped
        try {
          const rawEvt = JSON.parse(event.data as string) as { type?: string; message?: { content?: Array<{ type: string; text?: string }> } }
          if (rawEvt.type === 'assistant' && rawEvt.message?.content) {
            for (const block of rawEvt.message.content) {
              if (block.type === 'text' && block.text) {
                const sc = extractScorecardFromText(block.text)
                if (sc) setScorecard(sc as unknown as ScorecardResponse)
              }
            }
          }
        } catch {
          // ignore — best-effort scorecard extraction
        }

        const parsed = parseStreamMessage(event.data as string)
        if (parsed) {
          appendMessage(parsed)
        }
      }

      source.addEventListener('status', (event: MessageEvent) => {
        if (!mountedRef.current) return
        try {
          const parsed = JSON.parse(event.data as string) as { status?: string; message?: string }
          if (parsed.status) {
            setStatus(parsed.status as ContainerStatus)
          }
          if (parsed.message) {
            appendStatus(parsed.message)
          }
        } catch {
          // ignore
        }
      })

      source.addEventListener('done', (event: MessageEvent) => {
        if (!mountedRef.current) return
        source.close()
        eventSourceRef.current = null
        setIsThinking(false)
        try {
          const parsed = JSON.parse(event.data as string) as { message?: string; status?: string }
          const finalStatus = parsed.status === 'failed' ? 'failed' : 'completed'
          setStatus(finalStatus as ContainerStatus)
          if (finalStatus === 'failed') {
            setError(parsed.message ?? 'Session failed.')
          }
          appendStatus(parsed.message ?? 'Session completed.')
        } catch {
          setStatus('completed')
          appendStatus('Session completed.')
        }
        // Load scorecard after completion
        if (session?.id) {
          refreshSessionData(session.id)
        }
      })

      source.addEventListener('error', (event: Event) => {
        if (!mountedRef.current) return
        const isServerFramed =
          'data' in event && typeof (event as MessageEvent).data === 'string'

        if (isServerFramed) {
          source.close()
          eventSourceRef.current = null
          setStatus('failed')
          try {
            const parsed = JSON.parse((event as MessageEvent).data as string) as { message?: string }
            setError(parsed.message ?? 'Stream error')
            appendError(parsed.message ?? 'Stream error')
          } catch {
            setError('Stream error')
            appendError('Stream error')
          }
          return
        }

        if (source.readyState === EventSource.CLOSED) {
          eventSourceRef.current = null
          pollSessionStatus(sessionId)
        }
      })
    }

    init()

    return () => {
      abortController.abort()
      mountedRef.current = false
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
    }
  }, [installationId, repoFullName, prNumber, skillName, existingSessionId, appendMessage, appendStatus, appendError, refreshSessionData])

  const handleStop = useCallback(async () => {
    if (!session) return
    setStopping(true)
    try {
      await stopContainerSession(session.id)
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
      setStatus('stopped')
      appendStatus('Session stopped by user.')
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to stop'
      appendError(msg)
    } finally {
      setStopping(false)
    }
  }, [session, appendStatus, appendError])

  const handleSendMessage = useCallback(async () => {
    if (!session || !userInput.trim() || sending) return
    const content = userInput.trim()
    setSending(true)
    setUserInput('')
    setIsThinking(true)
    appendMessage({
      role: 'user',
      blocks: [{ type: 'text', text: content }],
    })
    try {
      await sendMessage(session.id, content)
    } catch (err) {
      if (err instanceof Error && err.message.includes('502')) {
        setStatus('completed')
        if (eventSourceRef.current) {
          eventSourceRef.current.close()
          eventSourceRef.current = null
        }
      } else {
        const msg = err instanceof Error ? err.message : 'Failed to send'
        appendError(msg)
      }
    } finally {
      setSending(false)
      inputRef.current?.focus()
    }
  }, [session, userInput, sending, appendMessage, appendError])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        handleSendMessage()
      }
    },
    [handleSendMessage],
  )

  const isRunning = status === 'running' || status === 'starting'
  const isTerminal = status === 'completed' || status === 'failed' || status === 'stopped'

  const statusVariant =
    isRunning ? 'ok' as const :
    status === 'completed' ? 'accent' as const :
    status === 'failed' ? 'danger' as const :
    'default' as const

  return (
    <div
      data-testid="container-session"
      className="h-screen bg-bg text-ink flex flex-col"
    >
      {/* Header */}
      <div className="h-14 flex items-center px-4 gap-3 shrink-0 border-b border-rule bg-bg2">
        <button
          onClick={onBack}
          data-testid="back-button"
          className="text-dim text-sm hover:text-ink2 transition-colors cursor-pointer font-mono"
        >
          {'\u2190'} Back
        </button>

        <span className="text-dim2">{'\u2502'}</span>

        <span className="text-ink text-sm font-sans">{session?.repo_full_name ?? repoFullName}</span>
        <span className="text-dim font-mono text-xs">#{session?.pr_number ?? prNumber}</span>

        <Chip variant="accent">{session?.skill_name ?? skillName}</Chip>

        {/* Status + controls right-aligned */}
        <div className="ml-auto flex items-center gap-2">
          <span data-testid="session-status"><Chip variant={statusVariant}>{status}</Chip></span>

          {isRunning && (
            <span
              onClick={handleStop}
              data-testid="stop-button"
              className={`cursor-pointer hover:brightness-125 transition-all ${stopping ? 'opacity-40 pointer-events-none' : ''}`}
            >
              <Chip variant="danger">{stopping ? 'stopping...' : 'stop'}</Chip>
            </span>
          )}
        </div>
      </div>

      {/* Error banner */}
      {error && isTerminal && (
        <div
          data-testid="error-banner"
          className="px-4 py-2 text-sm bg-danger/8 text-danger border-b border-danger/15"
        >
          {error}
        </div>
      )}

      {/* Main content: transcript + rail */}
      <div className="flex-1 min-h-0 flex">
        {/* Left: conversation transcript */}
        <div className="flex-1 min-w-0 flex flex-col">
          <div className="flex-1 min-h-0">
            <ConversationOutput messages={messages} isRunning={isRunning && isThinking} />
          </div>

          {/* Message input */}
          {isRunning && (
            <div className="shrink-0 px-4 py-3 flex items-center gap-3 border-t border-rule bg-bg2">
              <span className="text-accent font-mono text-sm select-none">{'\u276f'}</span>
              <input
                ref={inputRef}
                type="text"
                data-testid="message-input"
                value={userInput}
                onChange={(e) => setUserInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Type your answer..."
                disabled={sending}
                className="flex-1 bg-transparent text-ink text-sm font-sans outline-none placeholder:text-dim2 disabled:opacity-50"
                autoFocus
              />
              <Button
                data-testid="send-button"
                onClick={handleSendMessage}
                disabled={sending || !userInput.trim()}
              >
                {sending ? 'Sending...' : 'Send'}
              </Button>
            </div>
          )}

          {/* Post-session CTAs */}
          {isTerminal && status === 'completed' && (
            <div className="shrink-0 px-4 py-3 flex items-center gap-3 border-t border-rule bg-bg2">
              <Button onClick={onBack}>
                Challenge Again
              </Button>
              <Button variant="ghost" onClick={onBack}>
                {'\u2190'} Back to PR
              </Button>
            </div>
          )}
        </div>

        {/* Right rail */}
        <SessionRail
          session={session}
          status={status}
          scorecard={scorecard}
          questionCount={questionCount}
          currentQuestion={currentQuestion}
          isComplete={isTerminal}
        />
      </div>
    </div>
  )
}
