/**
 * TerminalOutput — renders streamed SSE output in a terminal-like panel.
 *
 * Dark background, monospace font, auto-scroll to bottom as new output
 * arrives. Amber accent for status indicators.
 */

import { useEffect, useRef } from 'react'
import type { TerminalLine } from './containerTypes'

interface TerminalOutputProps {
  lines: TerminalLine[]
  isRunning: boolean
}

export default function TerminalOutput({ lines, isRunning }: TerminalOutputProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const shouldAutoScrollRef = useRef(true)

  // Track whether user has scrolled up (disable auto-scroll).
  function handleScroll() {
    const el = containerRef.current
    if (!el) return
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    shouldAutoScrollRef.current = distanceFromBottom < 40
  }

  // Auto-scroll to bottom when new lines arrive.
  useEffect(() => {
    const el = containerRef.current
    if (el && shouldAutoScrollRef.current) {
      el.scrollTop = el.scrollHeight
    }
  }, [lines.length])

  return (
    <div
      data-testid="terminal-output"
      className="flex flex-col h-full"
      style={{ background: '#0D0D0D' }}
    >
      {/* Terminal header bar */}
      <div
        className="flex items-center gap-2 px-4 py-2 border-b"
        style={{
          borderColor: 'rgba(255, 255, 255, 0.06)',
          background: '#111111',
        }}
      >
        {/* macOS-style window dots */}
        <div className="flex gap-1.5">
          <span className="w-3 h-3 rounded-full" style={{ background: '#FF5F57' }} />
          <span className="w-3 h-3 rounded-full" style={{ background: '#FEBC2E' }} />
          <span className="w-3 h-3 rounded-full" style={{ background: '#28C840' }} />
        </div>
        <span
          className="text-[12px] font-mono ml-2"
          style={{ color: 'rgba(255, 255, 255, 0.4)' }}
        >
          helPRs session
        </span>
        {isRunning && (
          <span
            data-testid="terminal-running-indicator"
            className="ml-auto text-[11px] font-mono flex items-center gap-1.5"
            style={{ color: '#E2A039' }}
          >
            <span className="inline-block w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: '#E2A039' }} />
            running
          </span>
        )}
      </div>

      {/* Terminal body */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto overflow-x-hidden p-4 font-mono text-[13px] leading-relaxed"
        style={{ color: '#E0E0E0' }}
        role="log"
        aria-live="polite"
        aria-label="Terminal output"
      >
        {lines.length === 0 && !isRunning && (
          <p className="text-text-muted text-[13px]">No output yet.</p>
        )}
        {lines.map((line) => (
          <div
            key={line.id}
            className="whitespace-pre-wrap break-words"
            style={
              line.kind === 'error'
                ? { color: '#ff6961' }
                : line.kind === 'status'
                  ? { color: '#9a9898', fontStyle: 'italic' }
                  : undefined
            }
          >
            {line.text}
          </div>
        ))}
        {isRunning && lines.length > 0 && (
          <span
            data-testid="terminal-cursor"
            className="inline-block w-2 h-4 animate-pulse"
            style={{ background: '#E2A039' }}
          />
        )}
      </div>
    </div>
  )
}
