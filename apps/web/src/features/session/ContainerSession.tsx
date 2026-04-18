/**
 * ContainerSession — manages the lifecycle of a container skill session.
 *
 * 1. POSTs to create a session
 * 2. Connects to SSE stream for real-time output
 * 3. Displays output as a conversation with markdown rendering
 * 4. Provides stop/back controls
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useAuthStore } from '../auth/store'
import {
  buildStreamUrl,
  createContainerSession,
  getContainerSession,
  getSessionEvents,
  sendMessage,
  stopContainerSession,
} from './containerApi'
import ConversationOutput from './ConversationOutput'
import {
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
  /** When set, loads an existing session instead of creating a new one. */
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
  }, [])

  /** Helper: append a system-role status message. */
  const appendStatus = useCallback((text: string, subtype?: string) => {
    appendMessage({
      role: 'system',
      blocks: [{ type: 'text', text }],
      subtype,
    })
  }, [appendMessage])

  /** Helper: append an error message. */
  const appendError = useCallback((text: string) => {
    appendMessage({
      role: 'result',
      blocks: [{ type: 'text', text }],
      isError: true,
    })
  }, [appendMessage])

  // Create session on mount
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
        // Load an existing session (history view) instead of creating a new one
        if (existingSessionId) {
          const existing = await getContainerSession(existingSessionId)
          if (abortController.signal.aborted) return
          setSession(existing)
          setStatus(existing.status)

          const isTerminalStatus = ['completed', 'failed', 'timeout', 'stopped'].includes(existing.status)
          if (isTerminalStatus) {
            await loadStoredEvents(existing.id)
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

      // Exponential backoff: 2s, 4s, 8s, 16s, 32s
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

      // Default message event — parse Claude Code stream-json
      source.onmessage = (event: MessageEvent) => {
        if (!mountedRef.current) return
        if (event.lastEventId) {
          sseOffsetRef.current = parseInt(event.lastEventId, 10) || sseOffsetRef.current
        }

        // Track turn state: cursor pulses while Claude generates,
        // stops when a result event signals turn complete.
        try {
          const raw = JSON.parse(event.data as string) as { type?: string }
          if (raw.type === 'assistant') setIsThinking(true)
          else if (raw.type === 'result') setIsThinking(false)
        } catch {
          // ignore — thinking state is best-effort
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
          // ignore malformed status frames
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
  }, [installationId, repoFullName, prNumber, skillName, existingSessionId, appendMessage, appendStatus, appendError])

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
    // Show user's input as a user message in the conversation
    appendMessage({
      role: 'user',
      blocks: [{ type: 'text', text: content }],
    })
    try {
      await sendMessage(session.id, content)
    } catch (err) {
      // 502 means the container is already gone — session ended between
      // the last response and this send. Transition gracefully.
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

  return (
    <div
      data-testid="container-session"
      className="min-h-screen h-screen bg-primary text-text-primary flex flex-col"
    >
      {/* Header */}
      <div
        className="h-12 flex items-center px-4 gap-4 shrink-0 border-b"
        style={{ borderColor: 'rgba(255, 255, 255, 0.06)' }}
      >
        <button
          onClick={onBack}
          data-testid="back-button"
          className="text-text-secondary text-[13px] hover:text-text-primary transition-colors cursor-pointer"
        >
          &larr; Back
        </button>

        <span className="text-text-muted text-[12px]">|</span>

        <span className="text-text-primary text-[13px] font-sans">{repoFullName}</span>
        <span className="text-text-muted text-[12px]">#{prNumber}</span>

        <span
          className="text-[11px] px-2 py-0.5 rounded-full font-medium font-mono"
          style={{
            color: '#E2A039',
            background: 'rgba(226, 160, 57, 0.1)',
            border: '1px solid rgba(226, 160, 57, 0.2)',
          }}
        >
          {skillName}
        </span>

        {/* Status badge */}
        <span
          data-testid="session-status"
          className="text-[11px] px-2 py-0.5 rounded-full font-medium font-mono ml-auto"
          style={{
            color: isRunning
              ? '#30d158'
              : status === 'completed'
                ? '#E2A039'
                : status === 'failed'
                  ? '#ff3b30'
                  : '#9a9898',
            background: isRunning
              ? 'rgba(48, 209, 88, 0.1)'
              : status === 'completed'
                ? 'rgba(226, 160, 57, 0.1)'
                : status === 'failed'
                  ? 'rgba(255, 59, 48, 0.1)'
                  : 'rgba(154, 152, 152, 0.1)',
          }}
        >
          {status}
        </span>

        {/* Stop button */}
        {isRunning && (
          <button
            onClick={handleStop}
            disabled={stopping}
            data-testid="stop-button"
            className="text-[12px] font-semibold px-3 py-1 rounded-[6px] transition-all cursor-pointer disabled:opacity-50"
            style={{
              color: '#ff3b30',
              background: 'rgba(255, 59, 48, 0.1)',
              border: '1px solid rgba(255, 59, 48, 0.2)',
            }}
          >
            {stopping ? 'Stopping...' : 'Stop'}
          </button>
        )}
      </div>

      {/* Error banner */}
      {error && isTerminal && (
        <div
          data-testid="error-banner"
          className="px-4 py-2 text-[13px]"
          style={{
            background: 'rgba(255, 59, 48, 0.08)',
            color: '#ff6961',
            borderBottom: '1px solid rgba(255, 59, 48, 0.15)',
          }}
        >
          {error}
        </div>
      )}

      {/* Conversation output */}
      <div className="flex-1 min-h-0">
        <ConversationOutput messages={messages} isRunning={isRunning && isThinking} />
      </div>

      {/* Message input */}
      {isRunning && (
        <div
          className="shrink-0 px-4 py-3 flex items-center gap-3 border-t"
          style={{ borderColor: 'rgba(255, 255, 255, 0.06)', background: '#1a1717' }}
        >
          <span className="text-text-muted text-[13px] select-none">&gt;</span>
          <input
            ref={inputRef}
            type="text"
            data-testid="message-input"
            value={userInput}
            onChange={(e) => setUserInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type your answer..."
            disabled={sending}
            className="flex-1 bg-transparent text-text-primary text-[14px] font-sans outline-none placeholder:text-text-muted disabled:opacity-50"
            autoFocus
          />
          <button
            data-testid="send-button"
            onClick={handleSendMessage}
            disabled={sending || !userInput.trim()}
            className="text-[12px] font-semibold px-3 py-1 rounded-[6px] transition-all cursor-pointer disabled:opacity-30"
            style={{
              color: '#E2A039',
              background: 'rgba(226, 160, 57, 0.1)',
              border: '1px solid rgba(226, 160, 57, 0.2)',
            }}
          >
            {sending ? 'Sending...' : 'Send'}
          </button>
        </div>
      )}
    </div>
  )
}
