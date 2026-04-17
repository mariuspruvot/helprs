/**
 * ContainerSession — manages the lifecycle of a container skill session.
 *
 * 1. POSTs to create a session
 * 2. Connects to SSE stream for real-time output
 * 3. Displays output in a terminal panel
 * 4. Provides stop/back controls
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useAuthStore } from '../auth/store'
import {
  buildStreamUrl,
  createContainerSession,
  stopContainerSession,
} from './containerApi'
import TerminalOutput from './TerminalOutput'
import type {
  ContainerSessionResponse,
  ContainerStatus,
  TerminalLine,
} from './containerTypes'

interface ContainerSessionProps {
  installationId: string
  repoFullName: string
  prNumber: number
  skillName: string
  onBack: () => void
}

export default function ContainerSession({
  installationId,
  repoFullName,
  prNumber,
  skillName,
  onBack,
}: ContainerSessionProps) {
  const [session, setSession] = useState<ContainerSessionResponse | null>(null)
  const [lines, setLines] = useState<TerminalLine[]>([])
  const [status, setStatus] = useState<ContainerStatus>('pending')
  const [error, setError] = useState<string | null>(null)
  const [stopping, setStopping] = useState(false)

  const lineIdRef = useRef(0)
  const eventSourceRef = useRef<EventSource | null>(null)
  const mountedRef = useRef(true)

  const appendLine = useCallback((text: string) => {
    if (!mountedRef.current) return
    lineIdRef.current += 1
    const line: TerminalLine = {
      id: lineIdRef.current,
      text,
      timestamp: Date.now(),
    }
    setLines((prev) => [...prev, line])
  }, [])

  // Create session on mount
  useEffect(() => {
    mountedRef.current = true
    let cancelled = false

    async function init() {
      try {
        setStatus('starting')
        appendLine(`Starting ${skillName} for ${repoFullName}#${prNumber}...`)

        const created = await createContainerSession({
          installation_id: installationId,
          pr_number: prNumber,
          repo_full_name: repoFullName,
          skill_name: skillName,
        })

        if (cancelled) return

        setSession(created)
        setStatus(created.status)

        if (created.status === 'running' || created.status === 'starting') {
          connectStream(created.id)
        } else if (created.status === 'failed') {
          setError('Container failed to start')
          appendLine('[error] Container failed to start.')
        }
      } catch (err) {
        if (cancelled) return
        const msg = err instanceof Error ? err.message : 'Unknown error'
        setError(msg)
        setStatus('failed')
        appendLine(`[error] ${msg}`)
      }
    }

    function connectStream(sessionId: string) {
      const accessToken = useAuthStore.getState().accessToken
      if (!accessToken) {
        setError('Not authenticated')
        return
      }

      const url = buildStreamUrl(sessionId, accessToken)
      const source = new EventSource(url, { withCredentials: true })
      eventSourceRef.current = source

      source.addEventListener('open', () => {
        if (!mountedRef.current) return
        setStatus('running')
      })

      // Default message event — container output lines
      source.onmessage = (event: MessageEvent) => {
        if (!mountedRef.current) return
        appendLine(event.data as string)
      }

      // Typed events from the backend SSE stream
      source.addEventListener('output', (event: MessageEvent) => {
        if (!mountedRef.current) return
        try {
          const parsed = JSON.parse(event.data as string) as { text?: string }
          if (parsed.text) {
            appendLine(parsed.text)
          }
        } catch {
          // Raw text fallback
          appendLine(event.data as string)
        }
      })

      source.addEventListener('status', (event: MessageEvent) => {
        if (!mountedRef.current) return
        try {
          const parsed = JSON.parse(event.data as string) as { status?: string; message?: string }
          if (parsed.status) {
            setStatus(parsed.status as ContainerStatus)
          }
          if (parsed.message) {
            appendLine(`[status] ${parsed.message}`)
          }
        } catch {
          // ignore malformed status frames
        }
      })

      source.addEventListener('done', (event: MessageEvent) => {
        if (!mountedRef.current) return
        source.close()
        eventSourceRef.current = null
        setStatus('completed')
        try {
          const parsed = JSON.parse(event.data as string) as { message?: string }
          appendLine(parsed.message ?? 'Session completed.')
        } catch {
          appendLine('Session completed.')
        }
      })

      source.addEventListener('error', (event: Event) => {
        if (!mountedRef.current) return
        // Check if this is a server-framed error (MessageEvent with data)
        const isServerFramed =
          'data' in event && typeof (event as MessageEvent).data === 'string'

        if (isServerFramed) {
          source.close()
          eventSourceRef.current = null
          setStatus('failed')
          try {
            const parsed = JSON.parse((event as MessageEvent).data as string) as { message?: string }
            setError(parsed.message ?? 'Stream error')
            appendLine(`[error] ${parsed.message ?? 'Stream error'}`)
          } catch {
            setError('Stream error')
            appendLine('[error] Stream error')
          }
          return
        }

        // Native error — connection dropped
        if (source.readyState === EventSource.CLOSED) {
          eventSourceRef.current = null
          // Only mark as failed if we haven't already completed
          setStatus((prev) => (prev === 'completed' ? prev : 'failed'))
        }
      })
    }

    init()

    return () => {
      cancelled = true
      mountedRef.current = false
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
    }
  }, [installationId, repoFullName, prNumber, skillName, appendLine])

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
      appendLine('[stopped] Session stopped by user.')
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to stop'
      appendLine(`[error] ${msg}`)
    } finally {
      setStopping(false)
    }
  }, [session, appendLine])

  const isRunning = status === 'running' || status === 'starting'
  const isTerminal = status === 'completed' || status === 'failed' || status === 'stopped'

  return (
    <div
      data-testid="container-session"
      className="min-h-screen h-screen bg-primary text-text-primary font-mono flex flex-col"
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

        <span className="text-text-primary text-[13px]">{repoFullName}</span>
        <span className="text-text-muted text-[12px]">#{prNumber}</span>

        <span
          className="text-[11px] px-2 py-0.5 rounded-full font-medium"
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
          className="text-[11px] px-2 py-0.5 rounded-full font-medium ml-auto"
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

      {/* Terminal output */}
      <div className="flex-1 min-h-0">
        <TerminalOutput lines={lines} isRunning={isRunning} />
      </div>
    </div>
  )
}
